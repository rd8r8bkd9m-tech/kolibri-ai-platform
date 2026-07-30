"use client";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  createStoragePreview,
  executeStoragePreview,
  getStorageSnapshot,
  parseStoragePreview,
  reconcileStorageOperation,
  storageIdempotencyKey,
  StorageAdminRequestError,
  type StorageCategory,
  type StorageCleanupCategory,
  type StorageNode,
  type StoragePreview,
  type StoragePreviewInput,
} from "@/lib/platform-admin/storage-client";
import {
  storageAdminActionsLocked,
  storageConfirmationReady,
  storageExecutionFailureIsAmbiguous,
  storageNodeAllowsActions,
  storageOperationDisposition,
  storagePreviewTarget,
} from "@/lib/platform-admin/storage-ui-state";
import { cn } from "@/lib/utils";
import {
  Archive,
  CheckCircle2,
  Database,
  Eye,
  HardDrive,
  LoaderCircle,
  RefreshCw,
  RotateCcw,
  Server,
  ShieldCheck,
  Trash2,
  TriangleAlert,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";

const CATEGORY_LABELS: Record<StorageCleanupCategory, string> = {
  build: "Старые сборки",
  cache: "Кэши",
  log: "Ротационные логи",
  "stopped-container": "Остановленные контейнеры",
  "project-quarantine": "Карантин проектов",
};

const PROTECTION_LABELS = {
  "active-release": "Активный release",
  "current-symlink": "Ссылка current",
  "primary-database": "Основная база данных",
  "durable-volumes": "Постоянные volumes",
  "agent-runtime-state": "Состояние агентов",
} as const;

const OPERATION_STATUS_LABELS = {
  pending: "Ожидает сверки",
  succeeded: "Завершена",
  failed: "Отклонена",
} as const;

const AUDIT_ACTION_LABELS = {
  "storage.preview.created": "Создан preview",
  "storage.operation.succeeded": "Операция завершена",
  "storage.operation.failed": "Операция отклонена",
} as const;

const formatBytes = (value: number | null) => {
  if (value === null) return "—";
  if (value === 0) return "0 Б";
  const units = ["Б", "КиБ", "МиБ", "ГиБ", "ТиБ"];
  const exponent = Math.min(
    Math.floor(Math.log(value) / Math.log(1024)),
    units.length - 1,
  );
  return `${new Intl.NumberFormat("ru-RU", {
    maximumFractionDigits: exponent > 1 ? 2 : 0,
  }).format(value / 1024 ** exponent)} ${units[exponent]}`;
};

const formatDate = (value: number | null) =>
  value === null
    ? "не проверено"
    : new Date(value * 1000).toLocaleString("ru-RU", {
        day: "2-digit",
        month: "2-digit",
        year: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      });

type ActivePreview = {
  preview: StoragePreview;
  executeKey: string;
  recoveryRequired: boolean;
  pendingOperationId: string | null;
};

const PENDING_RECOVERY_KEY = "kolibri.storage.pending-recovery.v1";
const SAFE_EXECUTE_KEY =
  /^storage-execute:[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const SAFE_OPERATION_ID = /^sop_[0-9a-f]{32}$/;

const restorePendingRecovery = (): ActivePreview | null => {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(PENDING_RECOVERY_KEY);
    if (!raw || raw.length > 32_768) return null;
    const value = JSON.parse(raw) as unknown;
    if (!value || typeof value !== "object" || Array.isArray(value)) {
      return null;
    }
    const record = value as Record<string, unknown>;
    const preview = parseStoragePreview(record.preview);
    const executeKey =
      typeof record.executeKey === "string" ? record.executeKey : "";
    const pendingOperationId =
      record.pendingOperationId === null ||
      (typeof record.pendingOperationId === "string" &&
        SAFE_OPERATION_ID.test(record.pendingOperationId))
        ? record.pendingOperationId
        : undefined;
    if (
      !preview ||
      !SAFE_EXECUTE_KEY.test(executeKey) ||
      pendingOperationId === undefined ||
      record.recoveryRequired !== true
    ) {
      window.sessionStorage.removeItem(PENDING_RECOVERY_KEY);
      return null;
    }
    return {
      preview,
      executeKey,
      recoveryRequired: true,
      pendingOperationId,
    };
  } catch {
    return null;
  }
};

const persistPendingRecovery = (value: ActivePreview) => {
  if (typeof window === "undefined" || !value.recoveryRequired) return;
  try {
    window.sessionStorage.setItem(
      PENDING_RECOVERY_KEY,
      JSON.stringify(value),
    );
  } catch {
    // The live in-memory key still permits an idempotent retry.
  }
};

const clearPendingRecovery = () => {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.removeItem(PENDING_RECOVERY_KEY);
  } catch {
    // Storage may be disabled; there is nothing else to clear.
  }
};

export function StorageAdmin() {
  const [snapshot, setSnapshot] = useState<
    Awaited<ReturnType<typeof getStorageSnapshot>> | null
  >(null);
  const [loading, setLoading] = useState(true);
  const [snapshotStale, setSnapshotStale] = useState(false);
  const [busy, setBusy] = useState<
    "preview" | "execute" | "reconcile" | null
  >(null);
  const [error, setError] = useState<string | null>(null);
  const [operationError, setOperationError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [activePreview, setActivePreview] =
    useState<ActivePreview | null>(null);
  const [confirmation, setConfirmation] = useState("");

  const load = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    try {
      setSnapshot(await getStorageSnapshot(signal));
      setSnapshotStale(false);
      setError(null);
    } catch (requestError) {
      if (
        requestError instanceof DOMException &&
        requestError.name === "AbortError"
      ) {
        return;
      }
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Состояние хранилища недоступно.",
      );
      setSnapshotStale(true);
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  useEffect(() => {
    const recovery = restorePendingRecovery();
    if (!recovery) return;
    setActivePreview(recovery);
    setConfirmation("");
    setOperationError(
      `Нужно сверить незавершённую операцию${recovery.pendingOperationId ? ` ${recovery.pendingOperationId}` : ""}. Используется сохранённый ключ исходной попытки.`,
    );
  }, []);

  const beginPreview = async (input: StoragePreviewInput) => {
    setBusy("preview");
    setError(null);
    setOperationError(null);
    setMessage(null);
    try {
      const preview = await createStoragePreview(
        input,
        storageIdempotencyKey("preview"),
      );
      setActivePreview({
        preview,
        executeKey: storageIdempotencyKey("execute"),
        recoveryRequired: false,
        pendingOperationId: null,
      });
      setConfirmation("");
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Dry run не выполнен.",
      );
    } finally {
      setBusy(null);
    }
  };

  const reconcilePending = async (operationId: string) => {
    setBusy("reconcile");
    setOperationError(null);
    setMessage(null);
    try {
      const operation = await reconcileStorageOperation(operationId);
      const disposition = storageOperationDisposition(operation.status);
      if (disposition.alert === "success") {
        if (activePreview?.pendingOperationId === operationId) {
          clearPendingRecovery();
          setActivePreview(null);
          setConfirmation("");
        }
        setMessage(
          `Сверка подтверждена: операция ${operationId} завершена, освобождено ${formatBytes(operation.reclaimedBytes)}.`,
        );
      } else if (disposition.alert === "failed") {
        if (activePreview?.pendingOperationId === operationId) {
          clearPendingRecovery();
          setActivePreview(null);
          setConfirmation("");
        }
        setOperationError(
          `Журнал узла подтвердил отказ ${operationId}: ${operation.errorCode ?? "неизвестная ошибка"}.`,
        );
      } else {
        setOperationError(
          `Операция ${operationId} остаётся pending: ${operation.errorCode ?? "узел ещё применяет изменение"}. Сверка не запускала execute.`,
        );
      }
      await load();
    } catch (requestError) {
      setOperationError(
        requestError instanceof Error
          ? `${requestError.message} Execute не запускался; повторите серверную сверку позже.`
          : "Серверная сверка недоступна. Execute не запускался.",
      );
    } finally {
      setBusy(null);
    }
  };

  const execute = async () => {
    if (!activePreview) return;
    if (
      activePreview.recoveryRequired &&
      activePreview.pendingOperationId
    ) {
      await reconcilePending(activePreview.pendingOperationId);
      return;
    }
    const recoveryIntent = {
      ...activePreview,
      recoveryRequired: true,
    };
    setBusy("execute");
    setOperationError(null);
    setMessage(null);
    setActivePreview(recoveryIntent);
    persistPendingRecovery(recoveryIntent);
    try {
      const operation = await executeStoragePreview(
        activePreview.preview.id,
        activePreview.preview.confirmation,
        activePreview.executeKey,
      );
      const disposition = storageOperationDisposition(operation.status);
      if (disposition.alert === "success") {
        clearPendingRecovery();
        setMessage(
          `Операция завершена: ${operation.affectedItemCount} объектов, освобождено ${formatBytes(operation.reclaimedBytes)}.`,
        );
        setActivePreview(null);
        setConfirmation("");
      } else if (disposition.alert === "failed") {
        clearPendingRecovery();
        setOperationError(
          `Исполнитель подтвердил отказ: ${operation.errorCode ?? "неизвестная ошибка"}. Нужен новый preview.`,
        );
        setActivePreview(null);
        setConfirmation("");
      } else {
        const recovery = {
          ...activePreview,
          recoveryRequired: true,
          pendingOperationId: operation.id,
        };
        setActivePreview(recovery);
        persistPendingRecovery(recovery);
        setOperationError(
          `Результат операции ${operation.id} пока не подтверждён. Сервер сохранил ID: следующая сверка запросит только status и не повторит execute.`,
        );
      }
      await load();
    } catch (requestError) {
      if (
        requestError instanceof StorageAdminRequestError &&
        requestError.code === "storage_reauthentication_required"
      ) {
        if (!activePreview.recoveryRequired) {
          clearPendingRecovery();
          setActivePreview(activePreview);
        }
        setOperationError(
          activePreview.recoveryRequired
            ? "Нужен свежий вход владельца. Ключ незавершённой попытки сохранён в этой вкладке, но in-place step-up пока не подключён; для продолжения нужен доверенный оператор."
            : "Операция не началась: нужен свежий вход владельца, но in-place step-up пока не подключён. Выполнение остаётся заблокированным; для продолжения нужен доверенный оператор.",
        );
      } else if (
        requestError instanceof StorageAdminRequestError &&
        !storageExecutionFailureIsAmbiguous(requestError.status)
      ) {
        if (!activePreview.recoveryRequired) {
          clearPendingRecovery();
          setActivePreview(activePreview);
        }
        setOperationError(
          activePreview.recoveryRequired
            ? `${requestError.message} Новая попытка не началась; исход прежней операции всё ещё требует сверки.`
            : `${requestError.message} Операция на узле не начиналась; можно закрыть preview и создать новый.`,
        );
      } else {
        setActivePreview(recoveryIntent);
        setOperationError(
          requestError instanceof Error
            ? `${requestError.message} ID операции ещё не получен: сохранённый ключ нужен только для безопасного восстановления исходной попытки.`
            : "ID операции ещё не получен. Сохранённый ключ нужен для безопасного восстановления исходной попытки.",
        );
      }
    } finally {
      setBusy(null);
    }
  };

  const previewTarget = activePreview
    ? storagePreviewTarget(activePreview.preview, snapshot?.nodes ?? [])
    : null;
  const previewConsequence =
    activePreview?.preview.operationKind === "quarantine"
      ? "Проект будет перемещён в карантин. Это не освобождает место; его можно восстановить отдельным preview."
      : activePreview?.preview.operationKind === "restore"
        ? "Проект будет восстановлен из удерживаемого карантина. Введите RESTORE для подтверждения."
      : activePreview?.preview.operationKind === "purge"
        ? "Проект будет удалён из карантина необратимо. Восстановление после purge невозможно."
        : "Выбранные build/cache/log/container-объекты будут удалены необратимо.";

  return (
    <div data-slot="storage-admin">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="text-muted-foreground flex items-center gap-2 text-[13px]">
          <ShieldCheck className="size-4" aria-hidden="true" />
          Только allowlist-категории, всегда через preview
        </div>
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={loading || busy !== null}
          onClick={() => void load()}
          className="min-h-11 rounded-lg shadow-none sm:min-h-8"
        >
          <RefreshCw
            className={cn("size-4", loading && "animate-spin")}
            aria-hidden="true"
          />
          Обновить узлы
        </Button>
      </div>

      <div
        aria-live="polite"
        aria-atomic="true"
        className="mt-3"
      >
        {message ? (
          <p
            className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-[12px] text-emerald-700 dark:text-emerald-300"
            role="status"
          >
            {message}
          </p>
        ) : null}
        {error ? (
          <p
            className="border-destructive/30 text-destructive rounded-xl border px-3 py-2 text-[12px]"
            role="alert"
          >
            {error}
          </p>
        ) : null}
        {operationError ? (
          <p
            className="border-destructive/30 text-destructive mt-2 rounded-xl border px-3 py-2 text-[12px]"
            role="alert"
          >
            {operationError}
          </p>
        ) : null}
      </div>

      {loading && !snapshot ? (
        <div className="text-muted-foreground mt-5 flex items-center gap-2 text-[12px]">
          <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
          Читаем состояние Home и Primary
        </div>
      ) : null}

      {snapshot ? (
        <>
          <div className="mt-4 grid gap-4 xl:grid-cols-2">
            {snapshot.nodes.map((node) => (
              <StorageNodeCard
                key={node.id}
                node={node}
                disabled={
                  storageAdminActionsLocked({
                    busy: busy !== null,
                    loading,
                    snapshotStale,
                    hasActivePreview: activePreview !== null,
                  })
                }
                onPreview={beginPreview}
              />
            ))}
          </div>

          {!snapshotStale &&
          snapshot.nodes.every((node) => node.executorStatus === "ready") &&
          !snapshot.nodes.some(
            (node) =>
              node.categories.some((item) => item.itemCount > 0) ||
              node.projectCandidates.length > 0 ||
              node.quarantines.some((item) =>
                ["retained", "purge-eligible"].includes(item.status),
              ),
          ) ? (
            <p className="text-muted-foreground mt-4 rounded-2xl border p-4 text-[12px]">
              Кандидатов на очистку и удерживаемых проектов сейчас нет.
            </p>
          ) : null}

          <StorageHistory
            operations={snapshot.recentOperations}
            audit={snapshot.audit}
            busy={busy === "reconcile"}
            onReconcile={reconcilePending}
          />
        </>
      ) : null}

      <Dialog
        open={activePreview !== null}
        onOpenChange={(open) => {
          if (
            !open &&
            busy === null &&
            !activePreview?.recoveryRequired
          ) {
            setActivePreview(null);
            setConfirmation("");
          }
        }}
      >
        {activePreview ? (
          <DialogContent
            className="max-h-[90dvh] overflow-y-auto sm:max-w-2xl"
            showCloseButton={false}
          >
            <DialogHeader>
              <div className="flex items-start gap-3 text-left">
                <Eye
                  className="mt-0.5 size-5 shrink-0 text-amber-700 dark:text-amber-300"
                  aria-hidden="true"
                />
                <div>
                  <DialogTitle>
                    Dry run ·{" "}
                    {CATEGORY_LABELS[activePreview.preview.category]}
                  </DialogTitle>
                  <DialogDescription className="mt-2">
                    {activePreview.preview.nodeId === "home"
                      ? "Home"
                      : "Primary"}{" "}
                    · {activePreview.preview.candidateCount} объектов ·{" "}
                    {formatBytes(activePreview.preview.reclaimableBytes)} ·
                    истекает {formatDate(activePreview.preview.expiresAt)}
                  </DialogDescription>
                </div>
              </div>
            </DialogHeader>
            <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 px-3 py-2 text-[13px]">
              <p className="font-semibold">
                Цель: <span className="font-mono">{previewTarget}</span>
              </p>
              <p className="text-muted-foreground mt-1">
                {previewConsequence}
              </p>
            </div>
            {activePreview.recoveryRequired ? (
              <div
                className="border-destructive/30 text-destructive rounded-xl border px-3 py-2 text-[13px]"
                role="alert"
              >
                Сверка обязательна
                {activePreview.pendingOperationId
                  ? ` для ${activePreview.pendingOperationId}`
                  : ""}
                . Окно нельзя закрыть:{" "}
                {activePreview.pendingOperationId
                  ? "сервер запросит только status по operation ID и не вызовет execute."
                  : "operation ID ещё не получен, поэтому сохранённый ключ восстанавливает только исходную идемпотентную попытку."}
              </div>
            ) : null}
            <div className="grid gap-2 sm:grid-cols-2">
              {activePreview.preview.protectedScopes.map((scope) => (
                <div
                  key={scope}
                  className="flex items-center gap-2 rounded-lg border bg-background px-3 py-2 text-[12px]"
                >
                  <CheckCircle2
                    className="size-4 text-emerald-600"
                    aria-hidden="true"
                  />
                  {PROTECTION_LABELS[scope]} исключён
                </div>
              ))}
            </div>
            <label className="text-[13px] font-medium">
              Введите {activePreview.preview.confirmation}
              <Input
                autoFocus
                value={confirmation}
                autoComplete="off"
                spellCheck={false}
                onChange={(event) => setConfirmation(event.target.value)}
                className="mt-1.5 h-11 rounded-lg font-mono text-base shadow-none sm:h-9 sm:text-sm"
              />
            </label>
            <DialogFooter>
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={
                  busy !== null || activePreview.recoveryRequired
                }
                onClick={() => {
                  setActivePreview(null);
                  setConfirmation("");
                }}
                className="min-h-11 rounded-lg shadow-none sm:min-h-8"
              >
                {activePreview.recoveryRequired
                  ? "Сначала завершите сверку"
                  : "Отмена"}
              </Button>
              <Button
                type="button"
                size="sm"
                variant={
                  ["quarantine", "restore"].includes(
                    activePreview.preview.operationKind,
                  )
                    ? "default"
                    : "destructive"
                }
                disabled={
                  busy !== null ||
                  !storageConfirmationReady(
                    activePreview.preview,
                    confirmation,
                    Math.floor(Date.now() / 1000),
                    activePreview.recoveryRequired,
                  )
                }
                onClick={() => void execute()}
                className="min-h-11 rounded-lg shadow-none sm:min-h-8"
              >
                {busy === "execute" ? (
                  <LoaderCircle
                    className="size-4 animate-spin"
                    aria-hidden="true"
                  />
                ) : activePreview.preview.operationKind === "restore" ? (
                  <RotateCcw className="size-4" aria-hidden="true" />
                ) : activePreview.preview.operationKind === "quarantine" ? (
                  <Archive className="size-4" aria-hidden="true" />
                ) : (
                  <Trash2 className="size-4" aria-hidden="true" />
                )}
                {activePreview.preview.operationKind === "quarantine"
                  ? activePreview.recoveryRequired
                    ? "Сверить перемещение"
                    : "Переместить в карантин"
                  : activePreview.preview.operationKind === "restore"
                    ? activePreview.recoveryRequired
                      ? "Сверить восстановление"
                      : "Восстановить проект"
                    : activePreview.preview.operationKind === "purge"
                    ? activePreview.recoveryRequired
                      ? "Сверить удаление"
                      : "Удалить навсегда"
                    : activePreview.recoveryRequired
                      ? "Сверить очистку"
                      : "Удалить выбранное"}
              </Button>
            </DialogFooter>
          </DialogContent>
        ) : null}
      </Dialog>
    </div>
  );
}

function StorageNodeCard({
  disabled,
  node,
  onPreview,
}: {
  disabled: boolean;
  node: StorageNode;
  onPreview: (input: StoragePreviewInput) => Promise<void>;
}) {
  const actionsEnabled = storageNodeAllowsActions(node);
  return (
    <article className="rounded-2xl border bg-card p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <Server
            className="text-muted-foreground mt-0.5 size-5 shrink-0"
            aria-hidden="true"
          />
          <div className="min-w-0">
            <h4 className="text-[14px] font-semibold">{node.displayName}</h4>
            <p className="text-muted-foreground mt-1 text-[12px]">
              {node.executorStatus === "ready"
                ? `Проверено ${formatDate(node.scannedAt)}`
                : "Live-инвентаризация недоступна"}
            </p>
          </div>
        </div>
        <StorageStatus node={node} />
      </div>

      {node.executorStatus === "unavailable" ? (
        <div className="mt-3 flex gap-2 rounded-xl border border-amber-500/30 bg-amber-500/5 px-3 py-2 text-[13px] text-amber-800 dark:text-amber-200">
          <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          Исполнитель узла не подключён. Паспорт доступен только для чтения;
          preview и удаление физически не работают.
        </div>
      ) : node.executorStatus === "error" ? (
        <div className="border-destructive/30 text-destructive mt-3 rounded-xl border px-3 py-2 text-[13px]">
          Инвентаризация отклонена: {node.errorCode ?? "неизвестная ошибка"}.
        </div>
      ) : !node.executeEnabled ? (
        <div className="mt-3 rounded-xl border px-3 py-2 text-[13px]">
          Узел подключён только для чтения. Исполнение очистки выключено.
        </div>
      ) : null}

      <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3">
        <StorageMetric label="Всего FS" value={formatBytes(node.capacityBytes)} />
        <StorageMetric label="Занято FS" value={formatBytes(node.usedBytes)} />
        <StorageMetric label="Свободно FS" value={formatBytes(node.freeBytes)} />
      </div>

      {node.capacitySegments.length ? (
        <section className="mt-4" aria-label={`Сегменты ${node.displayName}`}>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h5 className="text-[13px] font-semibold">Сегменты ёмкости</h5>
            <span className="text-muted-foreground text-[12px]">
              {node.capacitySource === "live-executor"
                ? `live · ${formatDate(node.capacityObservedAt)}`
                : "паспорт конфигурации · не live"}
            </span>
          </div>
          <div className="mt-2 grid gap-2 sm:grid-cols-2">
            {node.capacitySegments.map((segment) => (
              <div
                key={segment.kind}
                className="rounded-xl border px-3 py-2"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[13px] font-medium">
                    {segment.displayName}
                  </span>
                  <Database
                    className="text-muted-foreground size-3.5"
                    aria-hidden="true"
                  />
                </div>
                <p className="mt-1 text-[15px] font-semibold">
                  {segment.displaySize}
                </p>
                <p className="text-muted-foreground mt-0.5 text-[12px]">
                  Только чтение. Размер томов здесь не меняется.
                </p>
              </div>
            ))}
          </div>
          {node.capacitySource === "configured-record" ? (
            <p className="text-muted-foreground mt-2 text-[12px]">
              Значения 210 GiB root LV и 19.83 GiB резерва VG взяты из
              паспорта узла, а не из текущего замера.
            </p>
          ) : null}
        </section>
      ) : null}

      <section className="mt-4" aria-label={`Очистка ${node.displayName}`}>
        <h5 className="text-[13px] font-semibold">Безопасная очистка</h5>
        <div className="mt-2 divide-y rounded-xl border px-3">
          {node.categories
            .filter((item) => item.category !== "project-quarantine")
            .map((item) => (
              <CategoryRow
                key={item.category}
                category={item}
                disabled={
                  disabled || !actionsEnabled || item.itemCount === 0
                }
                onPreview={() =>
                  onPreview({
                    nodeId: node.id,
                    category: item.category as Exclude<
                      StorageCleanupCategory,
                      "project-quarantine"
                    >,
                    operationKind: "cleanup",
                  })
                }
              />
            ))}
          {!node.categories.some(
            (item) => item.category !== "project-quarantine",
          ) ? (
            <p className="text-muted-foreground py-3 text-[12px]">
              Категории появятся после live-инвентаризации.
            </p>
          ) : null}
        </div>
      </section>

      <section className="mt-4" aria-label={`Проекты ${node.displayName}`}>
        <div className="flex items-center gap-2">
          <Archive className="text-muted-foreground size-4" aria-hidden="true" />
          <h5 className="text-[13px] font-semibold">Старые проекты</h5>
        </div>
        <p className="text-muted-foreground mt-1 text-[12px] leading-5">
          Сначала проект перемещается в карантин минимум на 7 дней. Restore
          доступен для удерживаемой записи через отдельный preview; purge
          остаётся необратимым и доступен только после retention.
        </p>
        <div className="mt-2 space-y-2">
          {node.projectCandidates.map((project) => (
            <div
              key={project.projectId}
              className="flex flex-col gap-2 rounded-xl border px-3 py-2 sm:flex-row sm:items-center sm:justify-between"
            >
              <div className="min-w-0">
                <p className="truncate text-[13px] font-medium">
                  {project.displayName}
                </p>
                <p className="text-muted-foreground mt-0.5 truncate text-[12px]">
                  {project.projectId} · {formatBytes(project.sizeBytes)} ·{" "}
                  {formatDate(project.lastModifiedAt)}
                </p>
              </div>
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={disabled || !actionsEnabled}
                onClick={() =>
                  void onPreview({
                    nodeId: node.id,
                    category: "project-quarantine",
                    operationKind: "quarantine",
                    projectId: project.projectId,
                  })
                }
                className="min-h-11 w-full rounded-lg shadow-none sm:min-h-8 sm:w-auto"
              >
                <Eye className="size-4" aria-hidden="true" />
                Preview карантина
              </Button>
            </div>
          ))}
          {!node.projectCandidates.length ? (
            <p className="text-muted-foreground rounded-xl border px-3 py-2 text-[12px]">
              Кандидатов на карантин нет.
            </p>
          ) : null}
        </div>
      </section>

      {node.quarantines.length ? (
        <section className="mt-4" aria-label={`Карантин ${node.displayName}`}>
          <h5 className="text-[13px] font-semibold">
            Удержание, restore и purge
          </h5>
          <div className="mt-2 space-y-2">
            {node.quarantines.map((item) => (
              <div
                key={item.id}
                className="flex flex-col gap-2 rounded-xl border px-3 py-2 sm:flex-row sm:items-center sm:justify-between"
              >
                <div className="min-w-0">
                  <p className="truncate text-[13px] font-medium">
                    {item.projectId}
                  </p>
                  <p className="text-muted-foreground mt-0.5 text-[12px]">
                    {item.status === "purged"
                      ? `Очищен ${formatDate(item.purgedAt)}`
                      : item.status === "restored"
                        ? `Восстановлен ${formatDate(item.restoredAt)}`
                        : `Хранить до ${formatDate(item.purgeEligibleAt)}`}
                  </p>
                </div>
                {["retained", "purge-eligible"].includes(item.status) ? (
                  <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row">
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      disabled={disabled || !actionsEnabled}
                      onClick={() =>
                        void onPreview({
                          nodeId: node.id,
                          category: "project-quarantine",
                          operationKind: "restore",
                          quarantineId: item.id,
                        })
                      }
                      className="min-h-11 w-full rounded-lg shadow-none sm:min-h-8 sm:w-auto"
                    >
                      <RotateCcw className="size-4" aria-hidden="true" />
                      Preview restore
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      disabled={
                        disabled ||
                        !actionsEnabled ||
                        item.status !== "purge-eligible"
                      }
                      onClick={() =>
                        void onPreview({
                          nodeId: node.id,
                          category: "project-quarantine",
                          operationKind: "purge",
                          quarantineId: item.id,
                        })
                      }
                      className="min-h-11 w-full rounded-lg shadow-none sm:min-h-8 sm:w-auto"
                    >
                      <Eye className="size-4" aria-hidden="true" />
                      {item.status === "purge-eligible"
                        ? "Preview purge"
                        : "Retention активен"}
                    </Button>
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        </section>
      ) : null}
    </article>
  );
}

function StorageStatus({ node }: { node: StorageNode }) {
  const ready = node.executorStatus === "ready" && node.executeEnabled;
  return (
    <span
      className={cn(
        "shrink-0 rounded-full border px-2 py-1 text-[12px] font-medium",
        ready &&
          "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
        !ready && "text-muted-foreground",
      )}
    >
      {ready
        ? "Preview + execute"
        : node.executorStatus === "ready"
          ? "Только чтение"
          : node.executorStatus === "unavailable"
            ? "Исполнитель не подключён"
            : "Ошибка inventory"}
    </span>
  );
}

function StorageMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border px-3 py-2">
      <p className="text-muted-foreground text-[12px]">{label}</p>
      <p className="mt-1 text-[13px] font-semibold">{value}</p>
    </div>
  );
}

function CategoryRow({
  category,
  disabled,
  onPreview,
}: {
  category: StorageCategory;
  disabled: boolean;
  onPreview: () => Promise<void>;
}) {
  return (
    <div className="flex flex-col gap-2 py-2.5 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <p className="text-[13px] font-medium">
          {CATEGORY_LABELS[category.category]}
        </p>
        <p className="text-muted-foreground mt-0.5 text-[12px]">
          {category.itemCount} объектов ·{" "}
          {formatBytes(category.reclaimableBytes)}
        </p>
      </div>
      <Button
        type="button"
        size="sm"
        variant="outline"
        disabled={disabled}
        onClick={() => void onPreview()}
        className="min-h-11 w-full rounded-lg shadow-none sm:min-h-8 sm:w-auto"
      >
        <Eye className="size-4" aria-hidden="true" />
        Preview
      </Button>
    </div>
  );
}

function StorageHistory({
  audit,
  busy,
  onReconcile,
  operations,
}: {
  audit: Awaited<ReturnType<typeof getStorageSnapshot>>["audit"];
  busy: boolean;
  onReconcile: (operationId: string) => Promise<void>;
  operations: Awaited<ReturnType<typeof getStorageSnapshot>>["recentOperations"];
}) {
  if (!operations.length && !audit.length) return null;
  return (
    <section className="mt-4 grid gap-3 lg:grid-cols-2">
      <div className="rounded-2xl border p-4">
        <div className="flex items-center gap-2">
          <HardDrive className="text-muted-foreground size-4" aria-hidden="true" />
          <h4 className="text-[13px] font-semibold">Последние операции</h4>
        </div>
        <div className="mt-2 divide-y">
          {operations.slice(0, 5).map((operation) => (
            <div
              key={operation.id}
              className="flex items-start justify-between gap-2 py-2 text-[12px]"
            >
              <div className="min-w-0">
                <p className="truncate font-medium">
                  {CATEGORY_LABELS[operation.category]} ·{" "}
                  {operation.nodeId === "home" ? "Home" : "Primary"}
                </p>
                <p className="text-muted-foreground mt-0.5 truncate">
                  {operation.id}
                </p>
              </div>
              {operation.status === "pending" ? (
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={busy}
                  onClick={() => void onReconcile(operation.id)}
                  className="min-h-9 shrink-0 rounded-lg shadow-none"
                >
                  {busy ? (
                    <LoaderCircle
                      className="size-3.5 animate-spin"
                      aria-hidden="true"
                    />
                  ) : (
                    <RefreshCw className="size-3.5" aria-hidden="true" />
                  )}
                  Сверить status
                </Button>
              ) : (
                <span className="shrink-0">
                  {OPERATION_STATUS_LABELS[operation.status]}
                </span>
              )}
            </div>
          ))}
        </div>
        {operations.some((operation) => operation.status === "pending") ? (
          <p className="text-muted-foreground mt-2 text-[12px] leading-5">
            Pending сверяется сервером по operation ID даже после потери
            sessionStorage. Кнопка вызывает только status и никогда не
            повторяет execute; локальный recovery остаётся оптимизацией до
            получения operation ID.
          </p>
        ) : null}
      </div>
      <div className="rounded-2xl border p-4">
        <div className="flex items-center gap-2">
          <ShieldCheck
            className="text-muted-foreground size-4"
            aria-hidden="true"
          />
          <h4 className="text-[13px] font-semibold">Аудит хранилища</h4>
        </div>
        <div className="mt-2 divide-y">
          {audit.slice(0, 5).map((event) => (
            <div key={event.id} className="py-2 text-[12px]">
              <div className="flex flex-wrap justify-between gap-2">
                <span className="font-medium">
                  {AUDIT_ACTION_LABELS[event.action]}
                </span>
                <time className="text-muted-foreground">
                  {formatDate(event.createdAt)}
                </time>
              </div>
              <p className="text-muted-foreground mt-0.5 truncate">
                {event.nodeId} · {event.targetRef}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
