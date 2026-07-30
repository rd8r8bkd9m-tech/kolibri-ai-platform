"use client";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  createTrustedAgentProfile,
  createTrustedAgentWorkspaceBinding,
  getTrustedAgentAuditPage,
  getTrustedAgentProfilesPage,
  getTrustedAgentWorkspaceBindingsPage,
  revokeTrustedAgentProfile,
  revokeTrustedAgentWorkspaceBinding,
  type TrustedAgentEnvironment,
  type TrustedAgentAuditEvent,
  type TrustedAgentProfile,
  type TrustedAgentWorkspaceBinding,
} from "@/lib/platform-admin/trusted-agents-client";
import {
  mergeBoundedFirstPage,
  useVisibleDocumentRefresh,
} from "@/lib/platform-admin/visible-document-refresh";
import { cn } from "@/lib/utils";
import {
  Bot,
  LoaderCircle,
  Plus,
  RefreshCw,
  ScrollText,
  Server,
  ShieldOff,
} from "lucide-react";
import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type FormEvent,
} from "react";

type TrustedAgentSnapshot = {
  bindings: TrustedAgentWorkspaceBinding[];
  profiles: TrustedAgentProfile[];
  audit: TrustedAgentAuditEvent[];
  bindingCursor: string | null;
  profileCursor: string | null;
  auditCursor: string | null;
};

type PageKind = "bindings" | "profiles" | "audit";
type RevokeTarget =
  | { kind: "binding"; id: string }
  | { kind: "profile"; id: string };

const mergeBindings = (
  current: TrustedAgentWorkspaceBinding[],
  incoming: TrustedAgentWorkspaceBinding[],
) => {
  const merged = new Map(current.map((item) => [item.id, item]));
  for (const item of incoming) merged.set(item.id, item);
  return [...merged.values()];
};

const mergeProfiles = (
  current: TrustedAgentProfile[],
  incoming: TrustedAgentProfile[],
) => {
  const merged = new Map(current.map((item) => [item.id, item]));
  for (const item of incoming) merged.set(item.id, item);
  return [...merged.values()];
};

const mergeAudit = (
  current: TrustedAgentAuditEvent[],
  incoming: TrustedAgentAuditEvent[],
) => {
  const merged = new Map(current.map((item) => [item.id, item]));
  for (const item of incoming) merged.set(item.id, item);
  return [...merged.values()];
};

const formatEpochTime = (value: number | null) =>
  value === null
    ? "—"
    : new Date(value * 1000).toLocaleString("ru-RU", {
        day: "2-digit",
        month: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      });

export function TrustedAgentAdmin() {
  const [snapshot, setSnapshot] = useState<TrustedAgentSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingPage, setLoadingPage] = useState<PageKind | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [revokeTarget, setRevokeTarget] = useState<RevokeTarget | null>(null);
  const [showBindingForm, setShowBindingForm] = useState(false);
  const [showProfileForm, setShowProfileForm] = useState(false);

  const load = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    try {
      const [bindings, profiles, audit] = await Promise.all([
        getTrustedAgentWorkspaceBindingsPage(undefined, signal),
        getTrustedAgentProfilesPage(undefined, signal),
        getTrustedAgentAuditPage(undefined, signal),
      ]);
      setSnapshot({
        bindings: bindings.items,
        profiles: profiles.items,
        audit: audit.items,
        bindingCursor: bindings.nextCursor,
        profileCursor: profiles.nextCursor,
        auditCursor: audit.nextCursor,
      });
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
          : "Контур доверенных агентов недоступен.",
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

  const refreshLiveAudit = useCallback(async (signal: AbortSignal) => {
    try {
      const page = await getTrustedAgentAuditPage(undefined, signal);
      setSnapshot((current) =>
        current
          ? {
              ...current,
              audit: mergeBoundedFirstPage(
                current.audit,
                page.items,
                (event) => event.id,
              ),
            }
          : current,
      );
    } catch (requestError) {
      if (
        requestError instanceof DOMException &&
        requestError.name === "AbortError"
      ) {
        return;
      }
    }
  }, []);

  useVisibleDocumentRefresh(refreshLiveAudit);

  const loadMore = async (kind: PageKind) => {
    if (!snapshot || loadingPage) return;
    const cursor =
      kind === "bindings"
        ? snapshot.bindingCursor
        : kind === "profiles"
          ? snapshot.profileCursor
          : snapshot.auditCursor;
    if (!cursor) return;
    setLoadingPage(kind);
    try {
      if (kind === "bindings") {
        const page = await getTrustedAgentWorkspaceBindingsPage(cursor);
        setSnapshot((current) =>
          current
            ? {
                ...current,
                bindings: mergeBindings(current.bindings, page.items),
                bindingCursor: page.nextCursor,
              }
            : current,
        );
      } else if (kind === "profiles") {
        const page = await getTrustedAgentProfilesPage(cursor);
        setSnapshot((current) =>
          current
            ? {
                ...current,
                profiles: mergeProfiles(current.profiles, page.items),
                profileCursor: page.nextCursor,
              }
            : current,
        );
      } else {
        const page = await getTrustedAgentAuditPage(cursor);
        setSnapshot((current) =>
          current
            ? {
                ...current,
                audit: mergeAudit(current.audit, page.items),
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
  };

  const activeBindings = useMemo(
    () =>
      snapshot?.bindings.filter(
        (binding) => binding.lifecycleStatus === "active",
      ) ?? [],
    [snapshot?.bindings],
  );

  const revoke = async (
    target: RevokeTarget,
    revision: number,
  ) => {
    const targetKey = `${target.kind}:${target.id}`;
    setBusy(targetKey);
    setError(null);
    setMessage(null);
    try {
      if (target.kind === "profile") {
        await revokeTrustedAgentProfile(target.id, revision);
        await load();
        setMessage("Полномочия агента отозваны. Новые dispatch запрещены.");
      } else {
        await revokeTrustedAgentWorkspaceBinding(target.id, revision);
        await load();
        setMessage(
          "Привязка узла и связанные полномочия отозваны терминально.",
        );
      }
      setRevokeTarget(null);
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Полномочия не отозваны.",
      );
    } finally {
      setBusy(null);
    }
  };

  return (
    <div data-slot="trusted-agent-admin">
      <div className="rounded-2xl border bg-card p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="max-w-2xl">
            <div className="flex items-center gap-2">
              <Bot className="text-muted-foreground size-5" aria-hidden="true" />
              <h4 className="text-[14px] font-semibold">
                Доверенные профили
              </h4>
            </div>
            <p className="text-muted-foreground mt-2 text-[12px] leading-5">
              Владелец делегирует профиль один раз. После назначения задачи
              агент выполняет её автономно с{" "}
              <code>full · danger-full-access · approval=never</code>, а
              прогресс, результаты и отзыв полномочий остаются в Kolibri.
            </p>
          </div>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={loading || busy !== null}
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
            className="border-destructive/30 text-destructive mt-4 rounded-xl border px-3 py-2 text-[11px]"
            role="alert"
          >
            {error}
          </p>
        ) : null}
        {message ? (
          <p
            className="mt-4 rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-[11px] text-emerald-700 dark:text-emerald-300"
            role="status"
          >
            {message}
          </p>
        ) : null}

        <div className="mt-4 flex flex-wrap gap-2">
          <Button
            type="button"
            size="sm"
            variant={showBindingForm ? "secondary" : "outline"}
            className="rounded-lg shadow-none"
            onClick={() => setShowBindingForm((open) => !open)}
          >
            <Plus className="size-4" aria-hidden="true" />
            Узел исполнения
          </Button>
          <Button
            type="button"
            size="sm"
            variant={showProfileForm ? "secondary" : "outline"}
            disabled={!activeBindings.length}
            className="rounded-lg shadow-none"
            onClick={() => setShowProfileForm((open) => !open)}
          >
            <Plus className="size-4" aria-hidden="true" />
            Профиль агента
          </Button>
        </div>

        {showBindingForm ? (
          <WorkspaceBindingForm
            disabled={busy !== null}
            onCreated={(binding) => {
              setSnapshot((current) =>
                current
                  ? {
                      ...current,
                      bindings: mergeBindings(current.bindings, [binding]),
                    }
                  : {
                      bindings: [binding],
                      profiles: [],
                      audit: [],
                      bindingCursor: null,
                      profileCursor: null,
                      auditCursor: null,
                    },
              );
              setShowBindingForm(false);
              setMessage("Узел исполнения привязан.");
              void load();
            }}
            onError={setError}
            onBusy={setBusy}
          />
        ) : null}

        {showProfileForm ? (
          <TrustedAgentProfileForm
            bindings={activeBindings}
            disabled={busy !== null}
            onCreated={(profile) => {
              setSnapshot((current) =>
                current
                  ? {
                      ...current,
                      profiles: mergeProfiles(current.profiles, [profile]),
                    }
                  : current,
              );
              setShowProfileForm(false);
              setMessage(
                "Доверенный профиль создан. Для его задач не требуется подтверждение каждой команды.",
              );
              void load();
            }}
            onError={setError}
            onBusy={setBusy}
          />
        ) : null}
      </div>

      {loading && !snapshot ? (
        <div className="text-muted-foreground mt-4 flex items-center gap-2 text-[12px]">
          <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
          Загружаем полномочия агентов
        </div>
      ) : null}

      {snapshot ? (
        <div className="mt-4 grid gap-4 xl:grid-cols-2">
          <AgentProfilesList
            items={snapshot.profiles}
            busy={busy}
            confirming={revokeTarget}
            onConfirm={setRevokeTarget}
            onRevoke={revoke}
          />
          <WorkspaceBindingsList
            items={snapshot.bindings}
            busy={busy}
            confirming={revokeTarget}
            onConfirm={setRevokeTarget}
            onRevoke={revoke}
          />
          <TrustedAgentLoadMore
            cursor={snapshot.profileCursor}
            loading={loadingPage === "profiles"}
            disabled={loadingPage !== null}
            label="профилей"
            onClick={() => void loadMore("profiles")}
          />
          <TrustedAgentLoadMore
            cursor={snapshot.bindingCursor}
            loading={loadingPage === "bindings"}
            disabled={loadingPage !== null}
            label="узлов"
            onClick={() => void loadMore("bindings")}
          />
          <TrustedAgentAudit items={snapshot.audit} />
          <TrustedAgentLoadMore
            cursor={snapshot.auditCursor}
            loading={loadingPage === "audit"}
            disabled={loadingPage !== null}
            label="событий"
            className="xl:col-span-2"
            onClick={() => void loadMore("audit")}
          />
        </div>
      ) : null}
    </div>
  );
}

const trustedAuditLabel = (action: TrustedAgentAuditEvent["action"]) => {
  if (action === "binding.created") return "Узел привязан";
  if (action === "binding.updated") return "Привязка узла обновлена";
  if (action === "binding.revoked") return "Узел отозван";
  if (action === "profile.created") return "Профиль создан";
  if (action === "profile.updated") return "Профиль обновлён";
  if (action === "profile.revoked") return "Профиль отозван";
  return "Профиль отозван вместе с узлом";
};

function TrustedAgentAudit({
  items,
}: {
  items: TrustedAgentAuditEvent[];
}) {
  return (
    <section className="xl:col-span-2" data-slot="trusted-agent-audit">
      <div className="mb-2 flex items-center gap-2">
        <ScrollText
          className="text-muted-foreground size-4"
          aria-hidden="true"
        />
        <h5 className="text-[12px] font-semibold">
          Журнал полномочий агентов
        </h5>
      </div>
      {items.length ? (
        <ol className="divide-y rounded-2xl border bg-card px-4">
          {items.map((event) => (
            <li key={event.id} className="py-3 text-[11px]">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="font-medium">
                    {trustedAuditLabel(event.action)}
                  </p>
                  <p className="text-muted-foreground mt-1 break-all text-[10px]">
                    {event.targetType} · {event.targetId} · revision{" "}
                    {event.targetRevision} · epoch {event.targetEpoch}
                  </p>
                </div>
                <time className="text-muted-foreground shrink-0 text-[10px]">
                  {formatEpochTime(event.createdAt)}
                </time>
              </div>
            </li>
          ))}
        </ol>
      ) : (
        <p className="text-muted-foreground rounded-2xl border p-4 text-[11px]">
          Событий полномочий пока нет.
        </p>
      )}
    </section>
  );
}

function WorkspaceBindingForm({
  disabled,
  onBusy,
  onCreated,
  onError,
}: {
  disabled: boolean;
  onBusy: (value: string | null) => void;
  onCreated: (binding: TrustedAgentWorkspaceBinding) => void;
  onError: (value: string | null) => void;
}) {
  const [environment, setEnvironment] =
    useState<TrustedAgentEnvironment>("development");
  const [fingerprintToken, setFingerprintToken] = useState("");

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    onBusy("create-binding");
    onError(null);
    try {
      onCreated(
        await createTrustedAgentWorkspaceBinding({
          environment,
          fingerprintToken: fingerprintToken.trim(),
        }),
      );
      setFingerprintToken("");
    } catch (requestError) {
      onError(
        requestError instanceof Error
          ? requestError.message
          : "Узел исполнения не привязан.",
      );
    } finally {
      onBusy(null);
    }
  };

  return (
    <form
      className="mt-4 grid gap-3 rounded-2xl border bg-background p-4 md:grid-cols-[12rem_minmax(0,1fr)_auto]"
      onSubmit={submit}
      aria-label="Привязать узел исполнения"
    >
      <label className="text-[11px] font-medium">
        Окружение
        <select
          value={environment}
          disabled={disabled}
          onChange={(event) =>
            setEnvironment(event.target.value as TrustedAgentEnvironment)
          }
          className="border-input bg-background mt-1.5 h-10 w-full rounded-xl border px-3 text-[12px]"
        >
          <option value="development">Development</option>
          <option value="staging">Staging</option>
          <option value="production">Production</option>
        </select>
      </label>
      <label className="text-[11px] font-medium">
        Fingerprint от Agent Host
        <Input
          value={fingerprintToken}
          disabled={disabled}
          onChange={(event) => setFingerprintToken(event.target.value)}
          placeholder="sha256:…"
          autoCapitalize="none"
          autoCorrect="off"
          spellCheck={false}
          className="mt-1.5 h-10 rounded-xl font-mono text-[11px] shadow-none"
        />
      </label>
      <Button
        type="submit"
        size="sm"
        disabled={disabled}
        className="h-10 self-end rounded-xl shadow-none"
      >
        {disabled ? (
          <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
        ) : null}
        Привязать
      </Button>
      <p className="text-muted-foreground text-[10px] leading-4 md:col-span-3">
        Передаётся только выданный Agent Host fingerprint. Путь к workspace и
        учётные данные в браузерный контракт не входят.
      </p>
    </form>
  );
}

function TrustedAgentProfileForm({
  bindings,
  disabled,
  onBusy,
  onCreated,
  onError,
}: {
  bindings: TrustedAgentWorkspaceBinding[];
  disabled: boolean;
  onBusy: (value: string | null) => void;
  onCreated: (profile: TrustedAgentProfile) => void;
  onError: (value: string | null) => void;
}) {
  const [bindingId, setBindingId] = useState(bindings[0]?.id ?? "");
  const [displayName, setDisplayName] = useState("Основной агент");
  const [runtimeProfile, setRuntimeProfile] = useState("codex-cli");
  const [agentCardId, setAgentCardId] = useState("codex-cli.primary");
  const [agentCardVersion, setAgentCardVersion] = useState("1");

  useEffect(() => {
    if (!bindings.some((binding) => binding.id === bindingId)) {
      setBindingId(bindings[0]?.id ?? "");
    }
  }, [bindingId, bindings]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    onBusy("create-profile");
    onError(null);
    try {
      onCreated(
        await createTrustedAgentProfile({
          workspaceBindingId: bindingId,
          displayName,
          runtimeProfile,
          agentCardId,
          agentCardVersion: Number(agentCardVersion),
        }),
      );
    } catch (requestError) {
      onError(
        requestError instanceof Error
          ? requestError.message
          : "Профиль агента не создан.",
      );
    } finally {
      onBusy(null);
    }
  };

  return (
    <form
      className="mt-4 grid gap-3 rounded-2xl border bg-background p-4 md:grid-cols-2"
      onSubmit={submit}
      aria-label="Создать доверенный профиль агента"
    >
      <label className="text-[11px] font-medium">
        Узел исполнения
        <select
          value={bindingId}
          disabled={disabled}
          onChange={(event) => setBindingId(event.target.value)}
          className="border-input bg-background mt-1.5 h-10 w-full rounded-xl border px-3 text-[12px]"
        >
          {bindings.map((binding) => (
            <option key={binding.id} value={binding.id}>
              {binding.environment} · {binding.serverRef}
            </option>
          ))}
        </select>
      </label>
      <TrustedAgentInput
        label="Название"
        value={displayName}
        disabled={disabled}
        onChange={setDisplayName}
      />
      <TrustedAgentInput
        label="Runtime profile"
        value={runtimeProfile}
        disabled={disabled}
        onChange={setRuntimeProfile}
      />
      <TrustedAgentInput
        label="Agent Card ID"
        value={agentCardId}
        disabled={disabled}
        onChange={setAgentCardId}
      />
      <TrustedAgentInput
        label="Версия Agent Card"
        value={agentCardVersion}
        disabled={disabled}
        inputMode="numeric"
        onChange={setAgentCardVersion}
      />
      <div className="flex items-end">
        <Button
          type="submit"
          size="sm"
          disabled={disabled || !bindingId}
          className="h-10 w-full rounded-xl shadow-none"
        >
          {disabled ? (
            <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
          ) : null}
          Создать автономный профиль
        </Button>
      </div>
      <p className="text-muted-foreground text-[10px] leading-4 md:col-span-2">
        Политика фиксирована сервером: full, danger-full-access,
        approval=never, concurrency=1. Она применяется только к назначенным
        задачам и привязанному Agent Host.
      </p>
    </form>
  );
}

function TrustedAgentInput({
  disabled,
  inputMode,
  label,
  onChange,
  value,
}: {
  disabled: boolean;
  inputMode?: "numeric";
  label: string;
  onChange: (value: string) => void;
  value: string;
}) {
  return (
    <label className="text-[11px] font-medium">
      {label}
      <Input
        value={value}
        disabled={disabled}
        inputMode={inputMode}
        autoCapitalize="none"
        autoCorrect="off"
        spellCheck={false}
        onChange={(event) => onChange(event.target.value)}
        className="mt-1.5 h-10 rounded-xl shadow-none"
      />
    </label>
  );
}

function AgentProfilesList({
  busy,
  confirming,
  items,
  onConfirm,
  onRevoke,
}: {
  busy: string | null;
  confirming: RevokeTarget | null;
  items: TrustedAgentProfile[];
  onConfirm: (target: RevokeTarget | null) => void;
  onRevoke: (target: RevokeTarget, revision: number) => Promise<void>;
}) {
  return (
    <section>
      <div className="mb-2 flex items-center gap-2">
        <Bot className="text-muted-foreground size-4" aria-hidden="true" />
        <h5 className="text-[12px] font-semibold">Профили агентов</h5>
      </div>
      <div className="space-y-3">
        {items.map((profile) => {
          const target = { kind: "profile", id: profile.id } as const;
          const confirmingThis =
            confirming?.kind === "profile" && confirming.id === profile.id;
          const busyThis = busy === `profile:${profile.id}`;
          return (
            <article
              key={profile.id}
              className="rounded-2xl border bg-card p-4"
            >
              <div className="flex min-w-0 items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="truncate text-[13px] font-semibold">
                    {profile.displayName}
                  </p>
                  <p className="text-muted-foreground mt-1 truncate text-[10px]">
                    {profile.runtimeProfile} · {profile.agentCardId} v
                    {profile.agentCardVersion}
                  </p>
                </div>
                <LifecycleBadge status={profile.lifecycleStatus} />
              </div>
              <dl className="mt-3 grid grid-cols-2 gap-3 text-[10px]">
                <TrustedAgentDatum
                  label="Политика"
                  value={`${profile.sandboxProfile} · ${profile.approvalPolicy}`}
                />
                <TrustedAgentDatum
                  label="Epoch"
                  value={`${profile.authorityEpoch}/${profile.profileEpoch}`}
                />
                <TrustedAgentDatum
                  label="Узел"
                  value={profile.workspaceBindingId}
                />
                <TrustedAgentDatum
                  label="Обновлён"
                  value={formatEpochTime(profile.updatedAt)}
                />
              </dl>
              {profile.lifecycleStatus === "active" ? (
                <RevokeControls
                  busy={busyThis}
                  confirming={confirmingThis}
                  label="Отозвать профиль"
                  onCancel={() => onConfirm(null)}
                  onRequest={() => onConfirm(target)}
                  onRevoke={() => void onRevoke(target, profile.revision)}
                />
              ) : null}
            </article>
          );
        })}
        {!items.length ? (
          <p className="text-muted-foreground rounded-2xl border p-4 text-[11px]">
            Доверенные профили пока не созданы.
          </p>
        ) : null}
      </div>
    </section>
  );
}

function WorkspaceBindingsList({
  busy,
  confirming,
  items,
  onConfirm,
  onRevoke,
}: {
  busy: string | null;
  confirming: RevokeTarget | null;
  items: TrustedAgentWorkspaceBinding[];
  onConfirm: (target: RevokeTarget | null) => void;
  onRevoke: (target: RevokeTarget, revision: number) => Promise<void>;
}) {
  return (
    <section>
      <div className="mb-2 flex items-center gap-2">
        <Server className="text-muted-foreground size-4" aria-hidden="true" />
        <h5 className="text-[12px] font-semibold">Узлы исполнения</h5>
      </div>
      <div className="space-y-3">
        {items.map((binding) => {
          const target = { kind: "binding", id: binding.id } as const;
          const confirmingThis =
            confirming?.kind === "binding" && confirming.id === binding.id;
          const busyThis = busy === `binding:${binding.id}`;
          return (
            <article
              key={binding.id}
              className="rounded-2xl border bg-card p-4"
            >
              <div className="flex min-w-0 items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="truncate text-[13px] font-semibold">
                    {binding.environment}
                  </p>
                  <p className="text-muted-foreground mt-1 truncate font-mono text-[10px]">
                    {binding.serverRef}
                  </p>
                </div>
                <LifecycleBadge status={binding.lifecycleStatus} />
              </div>
              <dl className="mt-3 grid grid-cols-2 gap-3 text-[10px]">
                <TrustedAgentDatum
                  label="Fingerprint"
                  value={`sha256:…${binding.fingerprintToken.slice(-8)}`}
                />
                <TrustedAgentDatum
                  label="Epoch"
                  value={`${binding.authorityEpoch}/${binding.workspaceEpoch}`}
                />
                <TrustedAgentDatum
                  label="Ревизия"
                  value={String(binding.revision)}
                />
                <TrustedAgentDatum
                  label="Обновлён"
                  value={formatEpochTime(binding.updatedAt)}
                />
              </dl>
              {binding.lifecycleStatus === "active" ? (
                <RevokeControls
                  busy={busyThis}
                  confirming={confirmingThis}
                  label="Отозвать узел"
                  onCancel={() => onConfirm(null)}
                  onRequest={() => onConfirm(target)}
                  onRevoke={() => void onRevoke(target, binding.revision)}
                />
              ) : null}
            </article>
          );
        })}
        {!items.length ? (
          <p className="text-muted-foreground rounded-2xl border p-4 text-[11px]">
            Узлы исполнения пока не привязаны.
          </p>
        ) : null}
      </div>
    </section>
  );
}

function RevokeControls({
  busy,
  confirming,
  label,
  onCancel,
  onRequest,
  onRevoke,
}: {
  busy: boolean;
  confirming: boolean;
  label: string;
  onCancel: () => void;
  onRequest: () => void;
  onRevoke: () => void;
}) {
  return (
    <div className="mt-4 flex flex-wrap justify-end gap-2 border-t pt-3">
      {confirming ? (
        <>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            disabled={busy}
            className="rounded-lg shadow-none"
            onClick={onCancel}
          >
            Отмена
          </Button>
          <Button
            type="button"
            size="sm"
            variant="destructive"
            disabled={busy}
            className="rounded-lg shadow-none"
            onClick={onRevoke}
          >
            {busy ? (
              <LoaderCircle
                className="size-4 animate-spin"
                aria-hidden="true"
              />
            ) : (
              <ShieldOff className="size-4" aria-hidden="true" />
            )}
            Подтвердить отзыв
          </Button>
        </>
      ) : (
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={busy}
          className="rounded-lg shadow-none"
          onClick={onRequest}
        >
          <ShieldOff className="size-4" aria-hidden="true" />
          {label}
        </Button>
      )}
    </div>
  );
}

function TrustedAgentDatum({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div className="min-w-0">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="mt-0.5 break-words font-medium">{value}</dd>
    </div>
  );
}

function LifecycleBadge({
  status,
}: {
  status: "active" | "revoked";
}) {
  return (
    <span
      className={cn(
        "shrink-0 rounded-full border px-2 py-1 text-[10px] font-medium",
        status === "active"
          ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
          : "text-muted-foreground",
      )}
    >
      {status === "active" ? "Активен" : "Отозван"}
    </span>
  );
}

function TrustedAgentLoadMore({
  className,
  cursor,
  disabled,
  label,
  loading,
  onClick,
}: {
  className?: string;
  cursor: string | null;
  disabled: boolean;
  label: string;
  loading: boolean;
  onClick: () => void;
}) {
  if (!cursor) return <span className={className} />;
  return (
    <Button
      type="button"
      variant="outline"
      size="sm"
      disabled={disabled}
      onClick={onClick}
      className={cn("w-fit rounded-lg shadow-none", className)}
    >
      {loading ? (
        <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
      ) : null}
      Ещё {label}
    </Button>
  );
}
