"use client";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { TrustedAgentAdmin } from "@/components/kolibri-shell/trusted-agent-admin";
import { StorageAdmin } from "@/components/kolibri-shell/storage-admin";
import {
  getPlatformAuditPage,
  getPlatformAdminSnapshot,
  getPlatformTenantsPage,
  getPlatformUsersPage,
  revokePlatformUserSessions,
  updatePlatformTenant,
  updatePlatformUser,
  type PlatformAuditEvent,
  type PlatformTenant,
  type PlatformUser,
} from "@/lib/platform-admin/client";
import {
  getAgentOperationsPage,
  type AgentOperation,
  type AgentProviderAvailability,
  type AgentRuntimeAvailability,
} from "@/lib/platform-admin/agent-operations-client";
import {
  mergeBoundedFirstPage,
  useVisibleDocumentRefresh,
} from "@/lib/platform-admin/visible-document-refresh";
import { cn } from "@/lib/utils";
import {
  Activity,
  Ban,
  Bot,
  Building2,
  HardDrive,
  LoaderCircle,
  RefreshCw,
  ScrollText,
  ShieldCheck,
  Users,
} from "lucide-react";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
} from "react";

type Snapshot = {
  tenants: PlatformTenant[];
  users: PlatformUser[];
  audit: PlatformAuditEvent[];
  operations: AgentOperation[];
  providers: AgentProviderAvailability[];
  runtimes: AgentRuntimeAvailability[];
  tenantCursor: string | null;
  userCursor: string | null;
  auditCursor: string | null;
  operationCursor: string | null;
  providersTruncated: boolean;
  runtimesTruncated: boolean;
};

type PageKind = "tenants" | "users" | "operations" | "audit";

const agentOperationKey = (operation: AgentOperation) =>
  `${operation.task.tenantId}:${operation.task.runId}`;

const mergeById = <T extends { id: string }>(
  current: T[],
  incoming: T[],
) => {
  const merged = new Map(current.map((item) => [item.id, item]));
  for (const item of incoming) merged.set(item.id, item);
  return [...merged.values()];
};

const mergeAgentOperations = (
  current: AgentOperation[],
  incoming: AgentOperation[],
) => {
  const merged = new Map(
    current.map((operation) => [agentOperationKey(operation), operation]),
  );
  for (const operation of incoming) {
    merged.set(agentOperationKey(operation), operation);
  }
  return [...merged.values()];
};

const terminalOperationAnnouncement = (operations: AgentOperation[]) => {
  if (operations.length === 1) {
    const operation = operations[0];
    return operation.status === "succeeded"
      ? `Агентная задача ${operation.task.runId} завершена успешно.`
      : `Агентная задача ${operation.task.runId} завершилась с ошибкой.`;
  }
  const succeeded = operations.filter(
    (operation) => operation.status === "succeeded",
  ).length;
  return `Завершено агентных задач: ${operations.length}. Успешно: ${succeeded}, с ошибкой: ${operations.length - succeeded}. Последняя: ${operations[0].task.runId}.`;
};

const parseOptionalInteger = (value: string) => {
  const normalized = value.trim();
  if (!normalized) return null;
  const parsed = Number(normalized);
  return Number.isSafeInteger(parsed) ? parsed : Number.NaN;
};

const parseIds = (value: string) => {
  const ids = value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  return ids.length ? [...new Set(ids)] : null;
};

export function PlatformAdminSection() {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tenantSearch, setTenantSearch] = useState("");
  const [userSearch, setUserSearch] = useState("");
  const [operationSearch, setOperationSearch] = useState("");
  const [auditSearch, setAuditSearch] = useState("");
  const [loadingPage, setLoadingPage] = useState<PageKind | null>(null);
  const [operationAnnouncement, setOperationAnnouncement] = useState("");
  const [agentLiveError, setAgentLiveError] = useState<string | null>(null);
  const [agentRefreshedAt, setAgentRefreshedAt] = useState<number | null>(null);
  const operationStatusesRef = useRef(
    new Map<string, AgentOperation["status"]>(),
  );

  const load = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    try {
      const [admin, operations] = await Promise.all([
        getPlatformAdminSnapshot(signal),
        getAgentOperationsPage(undefined, signal),
      ]);
      setSnapshot({
        ...admin,
        operations: operations.items,
        operationCursor: operations.nextCursor,
        providers: operations.availability.providers,
        providersTruncated: operations.availability.providersTruncated,
        runtimes: operations.availability.runtimes,
        runtimesTruncated: operations.availability.runtimesTruncated,
      });
      operationStatusesRef.current = new Map(
        operations.items.map((operation) => [
          agentOperationKey(operation),
          operation.status,
        ]),
      );
      setAgentRefreshedAt(Date.now());
      setAgentLiveError(null);
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
          : "Панель управления недоступна.",
      );
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  const refreshLiveAgentOperations = useCallback(
    async (signal: AbortSignal) => {
      if (loading || loadingPage === "operations") return;
      try {
        const page = await getAgentOperationsPage(undefined, signal);
        const terminalTransitions = page.items.filter(
          (operation) =>
            operationStatusesRef.current.get(agentOperationKey(operation)) ===
              "running" && operation.status !== "running",
        );
        setSnapshot((current) => {
          if (!current) return current;
          const operations = mergeBoundedFirstPage(
            current.operations,
            page.items,
            agentOperationKey,
          );
          operationStatusesRef.current = new Map(
            operations.map((operation) => [
              agentOperationKey(operation),
              operation.status,
            ]),
          );
          return {
            ...current,
            operations,
            providers: page.availability.providers,
            providersTruncated: page.availability.providersTruncated,
            runtimes: page.availability.runtimes,
            runtimesTruncated: page.availability.runtimesTruncated,
          };
        });
        if (terminalTransitions.length) {
          setOperationAnnouncement(
            terminalOperationAnnouncement(terminalTransitions),
          );
        }
        setAgentRefreshedAt(Date.now());
        setAgentLiveError(null);
      } catch (requestError) {
        if (
          requestError instanceof DOMException &&
          requestError.name === "AbortError"
        ) {
          return;
        }
        setAgentLiveError(
          "Автообновление агентных задач временно недоступно.",
        );
      }
    },
    [loading, loadingPage],
  );

  useVisibleDocumentRefresh(refreshLiveAgentOperations);

  const loadMore = useCallback(
    async (kind: PageKind) => {
      if (!snapshot || loadingPage) return;
      const cursor =
        kind === "tenants"
          ? snapshot.tenantCursor
          : kind === "users"
            ? snapshot.userCursor
            : kind === "operations"
              ? snapshot.operationCursor
              : snapshot.auditCursor;
      if (!cursor) return;
      setLoadingPage(kind);
      try {
        if (kind === "tenants") {
          const page = await getPlatformTenantsPage(cursor);
          setSnapshot((current) =>
            current
              ? {
                  ...current,
                  tenants: mergeById(current.tenants, page.items),
                  tenantCursor: page.nextCursor,
                }
              : current,
          );
        } else if (kind === "users") {
          const page = await getPlatformUsersPage(cursor);
          setSnapshot((current) =>
            current
              ? {
                  ...current,
                  users: mergeById(current.users, page.items),
                  userCursor: page.nextCursor,
                }
              : current,
          );
        } else if (kind === "operations") {
          const page = await getAgentOperationsPage(cursor);
          setSnapshot((current) =>
            current
              ? (() => {
                  const operations = mergeAgentOperations(
                    current.operations,
                    page.items,
                  );
                  operationStatusesRef.current = new Map(
                    operations.map((operation) => [
                      agentOperationKey(operation),
                      operation.status,
                    ]),
                  );
                  return {
                    ...current,
                    operations,
                    operationCursor: page.nextCursor,
                    providers: page.availability.providers,
                    providersTruncated:
                      page.availability.providersTruncated,
                    runtimes: page.availability.runtimes,
                    runtimesTruncated:
                      page.availability.runtimesTruncated,
                  };
                })()
              : current,
          );
        } else {
          const page = await getPlatformAuditPage(cursor);
          setSnapshot((current) =>
            current
              ? {
                  ...current,
                  audit: mergeById(current.audit, page.items),
                  auditCursor: page.nextCursor,
                }
              : current,
          );
        }
        setError(null);
      } catch (requestError) {
        setError(
          requestError instanceof Error
            ? requestError.message
            : "Следующая страница не загружена.",
        );
      } finally {
        setLoadingPage(null);
      }
    },
    [loadingPage, snapshot],
  );

  const replaceTenant = (next: PlatformTenant) =>
    setSnapshot((current) =>
      current
        ? {
            ...current,
            tenants: current.tenants.map((tenant) =>
              tenant.id === next.id ? next : tenant,
            ),
          }
        : current,
    );
  const replaceUser = (next: PlatformUser) =>
    setSnapshot((current) =>
      current
        ? {
            ...current,
            users: current.users.map((user) =>
              user.id === next.id ? next : user,
            ),
          }
        : current,
    );

  const activeTenants =
    snapshot?.tenants.filter(
      (tenant) => tenant.policy.lifecycleStatus === "active",
    ).length ?? 0;
  const activeSessions =
    snapshot?.tenants.reduce(
      (sum, tenant) => sum + tenant.activeSessionCount,
      0,
    ) ?? 0;
  const runningOperations =
    snapshot?.operations.filter((operation) => operation.status === "running")
      .length ?? 0;
  const filteredTenants = useMemo(() => {
    const query = tenantSearch.trim().toLocaleLowerCase("ru");
    if (!query) return snapshot?.tenants ?? [];
    return (snapshot?.tenants ?? []).filter((tenant) =>
      `${tenant.name} ${tenant.id} ${tenant.policy.planCode}`
        .toLocaleLowerCase("ru")
        .includes(query),
    );
  }, [snapshot?.tenants, tenantSearch]);
  const filteredUsers = useMemo(() => {
    const query = userSearch.trim().toLocaleLowerCase("ru");
    if (!query) return snapshot?.users ?? [];
    return (snapshot?.users ?? []).filter((user) =>
      `${user.name} ${user.email} ${user.id} ${user.tenantId}`
        .toLocaleLowerCase("ru")
        .includes(query),
    );
  }, [snapshot?.users, userSearch]);
  const filteredAudit = useMemo(() => {
    const query = auditSearch.trim().toLocaleLowerCase("ru");
    if (!query) return snapshot?.audit ?? [];
    return (snapshot?.audit ?? []).filter((event) =>
      `${event.action} ${event.targetType} ${event.targetId} ${event.targetTenantId}`
        .toLocaleLowerCase("ru")
        .includes(query),
    );
  }, [auditSearch, snapshot?.audit]);
  const filteredOperations = useMemo(() => {
    const query = operationSearch.trim().toLocaleLowerCase("ru");
    if (!query) return snapshot?.operations ?? [];
    return (snapshot?.operations ?? []).filter((operation) => {
      const policy = operation.frozenPolicy;
      return [
        operation.task.runId,
        operation.task.tenantId,
        operation.task.projectId,
        operation.agent.selectedProfile,
        operation.status,
        policy?.executionPlane,
        policy?.sandboxProfile,
        policy?.approvalPolicy,
      ]
        .filter(Boolean)
        .join(" ")
        .toLocaleLowerCase("ru")
        .includes(query);
    });
  }, [operationSearch, snapshot?.operations]);

  return (
    <section data-slot="platform-admin-control-plane">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <ShieldCheck
              className="text-muted-foreground size-5"
              aria-hidden="true"
            />
            <h2 className="text-2xl font-semibold tracking-[-0.025em]">
              Управление платформой
            </h2>
          </div>
          <p className="text-muted-foreground mt-2 max-w-2xl text-[13px] leading-5">
            Единый кабинет владельца: клиенты, агенты, рабочие пространства,
            тарифные лимиты и сессии. Доверенный профиль агента может штатно
            работать с полным доступом без подтверждения каждой команды.
            Выполнение остаётся наблюдаемым: задача, состояние, frozen-политика,
            журнал, отзыв полномочий и откат отделены от интерфейса агента.
          </p>
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={loading || loadingPage !== null}
          onClick={() => void load()}
          className="rounded-lg shadow-none"
        >
          <RefreshCw
            className={cn("size-4", loading && "animate-spin")}
            aria-hidden="true"
          />
          Обновить
        </Button>
      </div>

      {error ? (
        <p
          className="border-destructive/30 text-destructive mt-5 rounded-xl border px-3 py-2 text-[12px]"
          role="alert"
        >
          {error}
        </p>
      ) : null}

      {loading && !snapshot ? (
        <div className="text-muted-foreground mt-8 flex items-center gap-2 text-sm">
          <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
          Загружаем защищённый контур
        </div>
      ) : null}

      {snapshot ? (
        <>
          <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <MetricCard
              icon={Building2}
              label="Активные / загруженные пространства"
              value={`${activeTenants} / ${snapshot.tenants.length}`}
            />
            <MetricCard
              icon={Users}
              label="Загружено пользователей"
              value={String(snapshot.users.length)}
            />
            <MetricCard
              icon={ShieldCheck}
              label="Сессии загруженных клиентов"
              value={String(activeSessions)}
            />
            <MetricCard
              icon={Activity}
              label="Агентные задачи в работе"
              value={String(runningOperations)}
            />
          </div>

          <AdminGroup
            icon={Bot}
            title="Полномочия доверенных агентов"
            description="Постоянные привязки Agent Host и автономные профили, которые владелец назначает задачам без покомандных подтверждений."
          >
            <TrustedAgentAdmin />
          </AdminGroup>

          <AdminGroup
            icon={HardDrive}
            title="Хранилище"
            description="Наблюдение и безопасная очистка Home/Primary: только allowlist-категории, обязательный dry run, двухфазный карантин проектов и отдельный purge после retention."
          >
            <StorageAdmin />
          </AdminGroup>

          <AdminGroup
            icon={Bot}
            title="Агенты и выполнение"
            description="Фактические задачи, frozen-профили, очередь исполнения и доступные рантаймы. Данные читаются из рабочего контура, а не моделируются интерфейсом."
          >
            <div
              className="text-muted-foreground mb-3 flex flex-wrap items-center justify-between gap-2 text-[11px]"
              data-slot="agent-operations-live-state"
            >
              <span>Автообновление работает при активной вкладке</span>
              {agentRefreshedAt ? (
                <time dateTime={new Date(agentRefreshedAt).toISOString()}>
                  Обновлено{" "}
                  {new Date(agentRefreshedAt).toLocaleTimeString("ru-RU", {
                    hour: "2-digit",
                    minute: "2-digit",
                    second: "2-digit",
                  })}
                </time>
              ) : null}
            </div>
            <div
              aria-atomic="true"
              aria-live="polite"
              data-slot="agent-operation-announcement"
              role="status"
            >
              {operationAnnouncement ? (
                <p className="mb-3 rounded-xl border border-blue-500/30 bg-blue-500/10 px-3 py-2 text-[11px] text-blue-700 dark:text-blue-300">
                  {operationAnnouncement}
                </p>
              ) : null}
            </div>
            {agentLiveError ? (
              <p className="border-destructive/30 text-destructive mb-3 rounded-xl border px-3 py-2 text-[11px]">
                {agentLiveError}
              </p>
            ) : null}
            <AgentAvailability
              providers={snapshot.providers}
              providersTruncated={snapshot.providersTruncated}
              runtimes={snapshot.runtimes}
              runtimesTruncated={snapshot.runtimesTruncated}
            />
            <Input
              type="search"
              aria-label="Поиск агентных задач"
              value={operationSearch}
              onChange={(event) => setOperationSearch(event.target.value)}
              placeholder="Найти по задаче, tenant, профилю или политике"
              className="mb-3 h-10 rounded-xl shadow-none"
            />
            <div className="space-y-3">
              {filteredOperations.map((operation) => (
                <AgentOperationCard
                  key={`${operation.task.tenantId}:${operation.task.runId}`}
                  operation={operation}
                />
              ))}
              {!filteredOperations.length ? (
                <EmptyState text="Агентные задачи по этому запросу не найдены." />
              ) : null}
            </div>
            <LoadMoreButton
              cursor={snapshot.operationCursor}
              disabled={loadingPage !== null}
              loading={loadingPage === "operations"}
              noun="агентных задач"
              onClick={() => void loadMore("operations")}
            />
          </AdminGroup>

          <AdminGroup
            icon={Building2}
            title="Клиенты и политики"
            description="Статус tenant, тариф, лимит запусков, разрешённые модели и провайдеры."
          >
            <Input
              type="search"
              aria-label="Поиск клиентов"
              value={tenantSearch}
              onChange={(event) => setTenantSearch(event.target.value)}
              placeholder="Найти по клиенту, tenant ID или тарифу"
              className="mb-3 h-10 rounded-xl shadow-none"
            />
            <div className="space-y-3">
              {filteredTenants.map((tenant) => (
                <TenantPolicyCard
                  key={tenant.id}
                  tenant={tenant}
                  onUpdated={replaceTenant}
                />
              ))}
              {!filteredTenants.length ? (
                <EmptyState text="Клиенты по этому запросу не найдены." />
              ) : null}
            </div>
            <LoadMoreButton
              cursor={snapshot.tenantCursor}
              disabled={loadingPage !== null}
              loading={loadingPage === "tenants"}
              noun="клиентов"
              onClick={() => void loadMore("tenants")}
            />
          </AdminGroup>

          <AdminGroup
            icon={Users}
            title="Пользователи и сессии"
            description="Блокировка пользователя отзывает web и mobile сессии. Platform owner защищён от self-lockout."
          >
            <Input
              type="search"
              aria-label="Поиск пользователей"
              value={userSearch}
              onChange={(event) => setUserSearch(event.target.value)}
              placeholder="Найти по имени, email, user ID или tenant ID"
              className="mb-3 h-10 rounded-xl shadow-none"
            />
            <div className="space-y-3">
              {filteredUsers.map((user) => (
                <UserControlCard
                  key={user.id}
                  user={user}
                  onUpdated={replaceUser}
                />
              ))}
              {!filteredUsers.length ? (
                <EmptyState text="Пользователи по этому запросу не найдены." />
              ) : null}
            </div>
            <LoadMoreButton
              cursor={snapshot.userCursor}
              disabled={loadingPage !== null}
              loading={loadingPage === "users"}
              noun="пользователей"
              onClick={() => void loadMore("users")}
            />
          </AdminGroup>

          <AdminGroup
            icon={ScrollText}
            title="Журнал аудита"
            description="Последние подтверждённые изменения без паролей, токенов и provider secrets."
          >
            <Input
              type="search"
              aria-label="Поиск в журнале аудита"
              value={auditSearch}
              onChange={(event) => setAuditSearch(event.target.value)}
              placeholder="Найти по действию, типу или target ID"
              className="mb-3 h-10 rounded-xl shadow-none"
            />
            {filteredAudit.length ? (
              <ol className="divide-y rounded-2xl border bg-card px-4">
                {filteredAudit.map((event) => (
                  <li key={event.id} className="py-3 text-[12px]">
                    <div className="flex flex-wrap justify-between gap-2">
                      <span className="font-medium">{event.action}</span>
                      <time className="text-muted-foreground">
                        {new Date(event.createdAt * 1000).toLocaleString(
                          "ru-RU",
                        )}
                      </time>
                    </div>
                    <p className="text-muted-foreground mt-1 truncate">
                      {event.targetType}: {event.targetId}
                    </p>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="text-muted-foreground rounded-2xl border p-4 text-[12px]">
                События по этому запросу не найдены.
              </p>
            )}
            <LoadMoreButton
              cursor={snapshot.auditCursor}
              disabled={loadingPage !== null}
              loading={loadingPage === "audit"}
              noun="событий аудита"
              onClick={() => void loadMore("audit")}
            />
          </AdminGroup>
        </>
      ) : null}
    </section>
  );
}

const formatAgentTime = (value: string | null) => {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "—"
    : date.toLocaleString("ru-RU", {
        day: "2-digit",
        month: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      });
};

function AgentAvailability({
  providers,
  providersTruncated,
  runtimes,
  runtimesTruncated,
}: {
  providers: AgentProviderAvailability[];
  providersTruncated: boolean;
  runtimes: AgentRuntimeAvailability[];
  runtimesTruncated: boolean;
}) {
  return (
    <div className="mb-4 grid gap-3 lg:grid-cols-2">
      <article className="rounded-2xl border bg-card p-4">
        <div className="flex items-center justify-between gap-3">
          <h4 className="text-[13px] font-semibold">Рантаймы</h4>
          <span className="text-muted-foreground text-[11px]">
            {runtimes.length}
            {runtimesTruncated ? "+" : ""}
          </span>
        </div>
        <div className="mt-3 space-y-2">
          {runtimes.map((runtime) => (
            <div
              key={`${runtime.profileId}:${runtime.runtimeId}`}
              className="flex min-w-0 items-start justify-between gap-3 rounded-xl border px-3 py-2"
            >
              <div className="min-w-0">
                <p className="truncate text-[12px] font-medium">
                  {runtime.displayName}
                </p>
                <p className="text-muted-foreground mt-0.5 truncate text-[10px]">
                  {runtime.profileId} · {runtime.modes.join(", ")}
                </p>
              </div>
              <AgentStateBadge
                state={
                  runtime.startupStatus === "start_failed"
                    ? "failed"
                    : "ready"
                }
                label={
                  runtime.startupStatus === "start_failed"
                    ? "Ошибка запуска"
                    : "Зарегистрирован"
                }
              />
            </div>
          ))}
          {!runtimes.length ? (
            <p className="text-muted-foreground text-[11px]">
              Зарегистрированные рантаймы не обнаружены.
            </p>
          ) : null}
        </div>
      </article>
      <article className="rounded-2xl border bg-card p-4">
        <div className="flex items-center justify-between gap-3">
          <h4 className="text-[13px] font-semibold">Подключения моделей</h4>
          <span className="text-muted-foreground text-[11px]">
            {providers.length}
            {providersTruncated ? "+" : ""}
          </span>
        </div>
        <div className="mt-3 space-y-2">
          {providers.map((provider) => (
            <div
              key={`${provider.tenantId}:${provider.profileId}`}
              className="flex min-w-0 items-start justify-between gap-3 rounded-xl border px-3 py-2"
            >
              <div className="min-w-0">
                <p className="truncate text-[12px] font-medium">
                  {provider.profileId}
                </p>
                <p className="text-muted-foreground mt-0.5 truncate text-[10px]">
                  tenant {provider.tenantId} ·{" "}
                  {provider.authorityObserved
                    ? "полномочия подтверждены"
                    : "полномочия не подтверждены"}
                </p>
              </div>
              <AgentStateBadge
                state={
                  provider.status === "active" ||
                  provider.status === "connected"
                    ? "ready"
                    : provider.status === "error"
                      ? "failed"
                      : "neutral"
                }
                label={provider.status}
              />
            </div>
          ))}
          {!providers.length ? (
            <p className="text-muted-foreground text-[11px]">
              Подключения моделей не обнаружены.
            </p>
          ) : null}
        </div>
      </article>
    </div>
  );
}

function AgentOperationCard({
  operation,
}: {
  operation: AgentOperation;
}) {
  const policy = operation.frozenPolicy;
  const dispatch = operation.dispatch;
  const statusLabel =
    operation.status === "running"
      ? "Выполняется"
      : operation.status === "succeeded"
        ? "Завершена"
        : "Ошибка";
  return (
    <article
      className="rounded-2xl border bg-card p-4"
      data-agent-operation={operation.task.runId}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h4 className="truncate text-[13px] font-semibold">
            Задача {operation.task.runId}
          </h4>
          <p className="text-muted-foreground mt-1 truncate text-[10px]">
            tenant {operation.task.tenantId} · проект{" "}
            {operation.task.projectId}
          </p>
        </div>
        <AgentStateBadge
          state={
            operation.status === "running"
              ? "running"
              : operation.status === "succeeded"
                ? "ready"
                : "failed"
          }
          label={statusLabel}
        />
      </div>
      <dl className="mt-4 grid gap-x-4 gap-y-3 text-[11px] sm:grid-cols-2 lg:grid-cols-4">
        <AgentDatum
          label="Runtime profile"
          value={operation.agent.selectedProfile}
        />
        <AgentDatum
          label="Доверенный профиль"
          value={
            policy?.trustedAgentProfileId
              ? `${policy.trustedAgentProfileId} · epoch ${policy.trustedAgentProfileEpoch}`
              : "Не назначен"
          }
        />
        <AgentDatum
          label="Политика выполнения"
          value={
            policy
              ? `${policy.sandboxProfile} · approval=${policy.approvalPolicy}`
              : "Контекст ещё не зафиксирован"
          }
        />
        <AgentDatum
          label="Контур"
          value={
            policy
              ? `${policy.executionPlane} · ${policy.executionMode}`
              : "—"
          }
        />
        <AgentDatum
          label="Привязка Agent Host"
          value={
            policy?.trustedAgentWorkspaceBindingId
              ? `${policy.trustedAgentWorkspaceBindingId} · epoch ${policy.trustedAgentWorkspaceBindingEpoch}`
              : "—"
          }
        />
        <AgentDatum
          label="Очередь"
          value={
            dispatch
              ? `${dispatch.state} · ${dispatch.attempts}/${dispatch.maxAttempts}`
              : "Без команды в очереди"
          }
        />
        <AgentDatum
          label="Модель"
          value={
            policy?.modelIdRedacted
              ? "Скрыта"
              : (policy?.modelId ?? "По профилю")
          }
        />
        <AgentDatum
          label="Последняя активность"
          value={formatAgentTime(operation.timestamps.heartbeatAt)}
        />
        <AgentDatum
          label="События"
          value={String(operation.lastEventSequence)}
        />
        <AgentDatum
          label="Результат"
          value={
            operation.outcome ??
            operation.errorCode ??
            (operation.errorRedacted ? "Ошибка скрыта" : "—")
          }
        />
      </dl>
    </article>
  );
}

function AgentDatum({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="mt-0.5 break-words font-medium">{value}</dd>
    </div>
  );
}

function AgentStateBadge({
  label,
  state,
}: {
  label: string;
  state: "ready" | "running" | "failed" | "neutral";
}) {
  return (
    <span
      className={cn(
        "shrink-0 rounded-full border px-2 py-1 text-[10px] font-medium",
        state === "ready" &&
          "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
        state === "running" &&
          "border-blue-500/30 bg-blue-500/10 text-blue-700 dark:text-blue-300",
        state === "failed" &&
          "border-destructive/30 bg-destructive/10 text-destructive",
        state === "neutral" && "text-muted-foreground",
      )}
    >
      {label}
    </span>
  );
}

function MetricCard({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof Building2;
  label: string;
  value: string;
}) {
  return (
    <article className="rounded-2xl border bg-card p-4">
      <Icon className="text-muted-foreground size-4" aria-hidden="true" />
      <p className="mt-3 text-xl font-semibold">{value}</p>
      <p className="text-muted-foreground mt-1 text-[11px]">{label}</p>
    </article>
  );
}

function LoadMoreButton({
  cursor,
  disabled,
  loading,
  noun,
  onClick,
}: {
  cursor: string | null;
  disabled: boolean;
  loading: boolean;
  noun: string;
  onClick: () => void;
}) {
  if (!cursor) return null;
  return (
    <div className="mt-3 flex flex-wrap items-center gap-3">
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={disabled}
        onClick={onClick}
        className="rounded-lg shadow-none"
      >
        {loading ? (
          <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
        ) : null}
        Загрузить ещё
      </Button>
      <p className="text-muted-foreground text-[11px]">
        Поиск охватывает уже загруженные страницы {noun}.
      </p>
    </div>
  );
}

function EmptyState({ text }: { text: string }) {
  return (
    <p className="text-muted-foreground rounded-2xl border p-4 text-[12px]">
      {text}
    </p>
  );
}

function AdminGroup({
  children,
  description,
  icon: Icon,
  title,
}: {
  children: React.ReactNode;
  description: string;
  icon: typeof Building2;
  title: string;
}) {
  return (
    <section className="mt-8 border-t pt-6">
      <div className="flex items-start gap-3">
        <Icon className="text-muted-foreground mt-0.5 size-5" aria-hidden="true" />
        <div>
          <h3 className="text-[14px] font-semibold">{title}</h3>
          <p className="text-muted-foreground mt-1 max-w-2xl text-[12px] leading-5">
            {description}
          </p>
        </div>
      </div>
      <div className="mt-4">{children}</div>
    </section>
  );
}

function TenantPolicyCard({
  onUpdated,
  tenant,
}: {
  onUpdated: (tenant: PlatformTenant) => void;
  tenant: PlatformTenant;
}) {
  const [planCode, setPlanCode] = useState(tenant.policy.planCode);
  const [userLimit, setUserLimit] = useState(
    tenant.policy.userLimit?.toString() ?? "",
  );
  const [runLimit, setRunLimit] = useState(
    tenant.policy.monthlyRunLimit?.toString() ?? "",
  );
  const [models, setModels] = useState(
    tenant.policy.allowedModelIds?.join(", ") ?? "",
  );
  const [providers, setProviders] = useState(
    tenant.policy.allowedProviderIds?.join(", ") ?? "",
  );
  const [developerEnabled, setDeveloperEnabled] = useState(
    tenant.policy.developerAccessEnabled,
  );
  const [suspended, setSuspended] = useState(
    tenant.policy.lifecycleStatus === "suspended",
  );
  const [reason, setReason] = useState(tenant.policy.blockReason ?? "");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const parsedUserLimit = parseOptionalInteger(userLimit);
    const parsedRunLimit = parseOptionalInteger(runLimit);
    if (
      Number.isNaN(parsedUserLimit) ||
      Number.isNaN(parsedRunLimit) ||
      (suspended && !reason.trim())
    ) {
      setFailed(true);
      setMessage("Проверьте лимиты и укажите причину приостановки.");
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      const updated = await updatePlatformTenant(tenant.id, {
        revision: tenant.policy.revision,
        lifecycleStatus: suspended ? "suspended" : "active",
        planCode: planCode.trim(),
        userLimit: parsedUserLimit,
        monthlyRunLimit: parsedRunLimit,
        developerAccessEnabled: developerEnabled,
        allowedModelIds: parseIds(models),
        allowedProviderIds: parseIds(providers),
        blockReason: suspended ? reason.trim() : null,
      });
      onUpdated(updated);
      setFailed(false);
      setMessage("Политика сохранена.");
    } catch (requestError) {
      setFailed(true);
      setMessage(
        requestError instanceof Error
          ? requestError.message
          : "Политика не сохранена.",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <form
      onSubmit={submit}
      className="rounded-2xl border bg-card p-4"
      aria-label={`Политика ${tenant.name}`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h4 className="truncate text-[14px] font-semibold">{tenant.name}</h4>
          <p className="text-muted-foreground mt-1 truncate text-[11px]">
            {tenant.id} · {tenant.userCount} польз. ·{" "}
            {tenant.activeSessionCount} сесс.
          </p>
        </div>
        <label className="flex items-center gap-2 text-[12px]">
          <input
            type="checkbox"
            checked={developerEnabled}
            onChange={(event) => setDeveloperEnabled(event.target.checked)}
            className="size-4"
          />
          Operator mode gate
        </label>
      </div>
      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        <LabeledInput label="Тариф" value={planCode} onChange={setPlanCode} />
        <LabeledInput
          label="Плановый лимит пользователей (не блокирует)"
          value={userLimit}
          onChange={setUserLimit}
          inputMode="numeric"
          placeholder="Без лимита"
        />
        <LabeledInput
          label="Запусков в месяц"
          value={runLimit}
          onChange={setRunLimit}
          inputMode="numeric"
          placeholder="Без лимита"
        />
      </div>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <LabeledInput
          label="Разрешённые модели"
          value={models}
          onChange={setModels}
          placeholder="Все catalog-approved"
        />
        <LabeledInput
          label="Разрешённые провайдеры"
          value={providers}
          onChange={setProviders}
          placeholder="Все подключённые"
        />
      </div>
      <div className="mt-3 flex flex-wrap items-end gap-3">
        <label className="flex items-center gap-2 pb-2 text-[12px]">
          <input
            type="checkbox"
            checked={suspended}
            onChange={(event) => setSuspended(event.target.checked)}
            className="size-4"
          />
          Приостановить
        </label>
        <div className="min-w-[220px] flex-1">
          <LabeledInput
            label="Причина блокировки"
            value={reason}
            onChange={setReason}
            placeholder="Обязательна при приостановке"
          />
        </div>
        <Button
          type="submit"
          size="sm"
          disabled={busy}
          className="rounded-lg shadow-none"
        >
          {busy ? <LoaderCircle className="size-4 animate-spin" /> : null}
          Сохранить
        </Button>
      </div>
      <StatusMessage failed={failed} message={message} />
    </form>
  );
}

function UserControlCard({
  onUpdated,
  user,
}: {
  onUpdated: (user: PlatformUser) => void;
  user: PlatformUser;
}) {
  const [accessStatus, setAccessStatus] = useState(user.control.accessStatus);
  const [developerAccess, setDeveloperAccess] = useState(
    user.control.developerAccess,
  );
  const [reason, setReason] = useState(user.control.blockReason ?? "");
  const [busy, setBusy] = useState<"save" | "sessions" | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const protectedOwner = user.isPlatformOwner;

  const save = async () => {
    if (accessStatus === "blocked" && !reason.trim()) {
      setFailed(true);
      setMessage("Для блокировки укажите причину.");
      return;
    }
    setBusy("save");
    try {
      const updated = await updatePlatformUser(user.id, {
        revision: user.control.revision,
        accessStatus,
        developerAccess,
        blockReason: accessStatus === "blocked" ? reason.trim() : null,
      });
      onUpdated(updated);
      setFailed(false);
      setMessage("Настройки пользователя сохранены.");
    } catch (requestError) {
      setFailed(true);
      setMessage(
        requestError instanceof Error
          ? requestError.message
          : "Настройки не сохранены.",
      );
    } finally {
      setBusy(null);
    }
  };

  const revoke = async () => {
    setBusy("sessions");
    try {
      const count = await revokePlatformUserSessions(user.id);
      setFailed(false);
      setMessage(`Отозвано сессий: ${count}.`);
    } catch (requestError) {
      setFailed(true);
      setMessage(
        requestError instanceof Error
          ? requestError.message
          : "Сессии не отозваны.",
      );
    } finally {
      setBusy(null);
    }
  };

  return (
    <article className="rounded-2xl border bg-card p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h4 className="truncate text-[14px] font-semibold">
            {user.name}
            {protectedOwner ? " · Platform owner" : ""}
          </h4>
          <p className="text-muted-foreground mt-1 truncate text-[11px]">
            {user.email} · {user.activeSessionCount} сесс.
          </p>
        </div>
        <span className="text-muted-foreground rounded-full border px-2 py-1 text-[10px]">
          {user.role}
        </span>
      </div>
      <div className="mt-4 grid gap-3 sm:grid-cols-[1fr_1fr_2fr]">
        <label className="text-[11px] font-medium">
          Доступ
          <select
            value={accessStatus}
            disabled={protectedOwner}
            onChange={(event) =>
              setAccessStatus(event.target.value as typeof accessStatus)
            }
            className="border-input bg-background mt-1.5 h-9 w-full rounded-lg border px-3 text-[12px]"
          >
            <option value="active">Активен</option>
            <option value="blocked">Заблокирован</option>
          </select>
        </label>
        <label className="text-[11px] font-medium">
          Operator prerequisite (reserved)
          <select
            value={developerAccess}
            disabled={protectedOwner}
            onChange={(event) =>
              setDeveloperAccess(
                event.target.value as typeof developerAccess,
              )
            }
            className="border-input bg-background mt-1.5 h-9 w-full rounded-lg border px-3 text-[12px]"
          >
            <option value="inherit">По tenant</option>
            <option value="allow">Разрешить</option>
            <option value="deny">Запретить</option>
          </select>
        </label>
        <LabeledInput
          label="Причина блокировки"
          value={reason}
          onChange={setReason}
          disabled={protectedOwner}
        />
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button
          type="button"
          size="sm"
          disabled={protectedOwner || busy !== null}
          onClick={() => void save()}
          className="rounded-lg shadow-none"
        >
          {busy === "save" ? (
            <LoaderCircle className="size-4 animate-spin" />
          ) : null}
          Сохранить
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={protectedOwner || busy !== null}
          onClick={() => void revoke()}
          className="rounded-lg shadow-none"
        >
          {busy === "sessions" ? (
            <LoaderCircle className="size-4 animate-spin" />
          ) : (
            <Ban className="size-4" />
          )}
          Отозвать сессии
        </Button>
      </div>
      <StatusMessage failed={failed} message={message} />
    </article>
  );
}

function LabeledInput({
  disabled,
  inputMode,
  label,
  onChange,
  placeholder,
  value,
}: {
  disabled?: boolean;
  inputMode?: "numeric";
  label: string;
  onChange: (value: string) => void;
  placeholder?: string;
  value: string;
}) {
  return (
    <label className="block text-[11px] font-medium">
      {label}
      <Input
        value={value}
        disabled={disabled}
        inputMode={inputMode}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
        className="mt-1.5 h-9 rounded-lg text-[12px] shadow-none"
      />
    </label>
  );
}

function StatusMessage({
  failed,
  message,
}: {
  failed: boolean;
  message: string | null;
}) {
  return message ? (
    <p
      className={cn(
        "mt-3 text-[11px]",
        failed ? "text-destructive" : "text-muted-foreground",
      )}
      role={failed ? "alert" : "status"}
    >
      {message}
    </p>
  ) : null;
}
