"use client";

import {
	Activity,
	Ban,
	Bot,
	Building2,
	Check,
	CreditCard,
	HardDrive,
	KeyRound,
	LayoutDashboard,
	ListTodo,
	LoaderCircle,
	Plus,
	RefreshCw,
	ScrollText,
	Server,
	ShieldCheck,
	TestTube2,
	Trash2,
	Users,
} from "lucide-react";
import {
	type FormEvent,
	useCallback,
	useEffect,
	useMemo,
	useRef,
	useState,
} from "react";
import {
	AdminStatusBadge as AgentStateBadge,
	AdminEmptyState as EmptyState,
	AdminTextField as LabeledInput,
	AdminMetricCard as MetricCard,
	AdminStatusMessage as StatusMessage,
} from "@/components/kolibri-shell/admin/admin-primitives";
import { AgentTaskWorkspace } from "@/components/kolibri-shell/agent-task-workspace";
import { ConstructionAgentAdmin } from "@/components/kolibri-shell/construction-agent-admin";
import { StorageAdmin } from "@/components/kolibri-shell/storage-admin";
import { TrustedAgentAdmin } from "@/components/kolibri-shell/trusted-agent-admin";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
	type AgentOperation,
	type AgentProviderAvailability,
	type AgentRuntimeAvailability,
	getAgentOperationsPage,
} from "@/lib/platform-admin/agent-operations-client";
import {
	getPlatformAdminSnapshot,
	getPlatformAuditPage,
	getPlatformTenantsPage,
	getPlatformUsersPage,
	type PlatformAuditEvent,
	type PlatformTenant,
	type PlatformUser,
	revokePlatformUserSessions,
	updatePlatformTenant,
	updatePlatformUser,
} from "@/lib/platform-admin/client";
import {
	mergeBoundedFirstPage,
	useVisibleDocumentRefresh,
} from "@/lib/platform-admin/visible-document-refresh";
import {
	createPlatformModel,
	deletePlatformModel,
	type PlatformModel,
	type PlatformModelCreate,
	getPlatformModels,
	testPlatformModel,
	updatePlatformModel,
} from "@/lib/platform-admin/models-client";
import {
	getAdminBillingConfig,
	saveAdminBillingConfig,
	type BillingAdminConfig,
	type BillingAdminConfigUpdate,
} from "@/lib/billing/admin-client";
import { cn } from "@/lib/utils";

type Snapshot = {
	tenants: PlatformTenant[];
	users: PlatformUser[];
	audit: PlatformAuditEvent[];
	operations: AgentOperation[];
	providers: AgentProviderAvailability[];
	runtimes: AgentRuntimeAvailability[];
	platformModels: PlatformModel[];
	tenantCursor: string | null;
	userCursor: string | null;
	auditCursor: string | null;
	operationCursor: string | null;
	providersTruncated: boolean;
	runtimesTruncated: boolean;
};

type PageKind = "tenants" | "users" | "operations" | "audit";
type PlatformAdminView =
	"overview" | "hosts" | "agents" | "tasks" | "clients" | "models" | "billing" | "audit";

const PLATFORM_ADMIN_VIEWS: Array<{
	id: PlatformAdminView;
	label: string;
	icon: typeof ShieldCheck;
}> = [
	{ id: "overview", label: "Обзор", icon: LayoutDashboard },
	{ id: "hosts", label: "Хосты", icon: Server },
	{ id: "agents", label: "Агенты", icon: Bot },
	{ id: "tasks", label: "Задачи", icon: ListTodo },
	{ id: "clients", label: "Клиенты", icon: Users },
	{ id: "models", label: "Модели", icon: Bot },
	{ id: "billing", label: "Оплата", icon: CreditCard },
	{ id: "audit", label: "Аудит", icon: ScrollText },
];

const agentOperationKey = (operation: AgentOperation) =>
	`${operation.task.tenantId}:${operation.task.runId}`;

const mergeById = <T extends { id: string }>(current: T[], incoming: T[]) => {
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
	const [activeView, setActiveView] = useState<PlatformAdminView>("overview");
	const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState<string | null>(null);
	const [tenantSearch, setTenantSearch] = useState("");
	const [userSearch, setUserSearch] = useState("");
	const [operationSearch, setOperationSearch] = useState("");
	const [selectedOperationKey, setSelectedOperationKey] = useState<
		string | null
	>(null);
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
			const [admin, operations, models] = await Promise.all([
				getPlatformAdminSnapshot(signal),
				getAgentOperationsPage(undefined, signal),
				getPlatformModels(signal),
			]);
			setSnapshot({
				...admin,
				operations: operations.items,
				operationCursor: operations.nextCursor,
				providers: operations.availability.providers,
				providersTruncated: operations.availability.providersTruncated,
				runtimes: operations.availability.runtimes,
				runtimesTruncated: operations.availability.runtimesTruncated,
				platformModels: models,
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
				setAgentLiveError("Автообновление агентных задач временно недоступно.");
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
										providersTruncated: page.availability.providersTruncated,
										runtimes: page.availability.runtimes,
										runtimesTruncated: page.availability.runtimesTruncated,
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

	useEffect(() => {
		if (activeView !== "tasks") return;
		setSelectedOperationKey((current) =>
			filteredOperations.some(
				(operation) => agentOperationKey(operation) === current,
			)
				? current
				: filteredOperations[0]
					? agentOperationKey(filteredOperations[0])
					: null,
		);
	}, [activeView, filteredOperations]);

	return (
		<section data-slot="platform-admin-control-plane">
			<div className="flex flex-wrap items-start justify-between gap-4">
				<div className="flex items-center gap-2.5">
					<ShieldCheck
						className="text-muted-foreground size-5"
						aria-hidden="true"
					/>
					<h2 className="text-2xl font-semibold tracking-[-0.025em]">
						Управление платформой
					</h2>
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

			<nav
				aria-label="Разделы управления платформой"
				className="mt-4 overflow-x-auto border-b"
			>
				<div className="flex min-w-max gap-1" role="tablist">
					{PLATFORM_ADMIN_VIEWS.map((view) => {
						const Icon = view.icon;
						const selected = activeView === view.id;
						return (
							<button
								type="button"
								key={view.id}
								role="tab"
								aria-selected={selected}
								data-platform-admin-tab={view.id}
								onClick={() => setActiveView(view.id)}
								className={cn(
									"relative flex h-11 items-center gap-2 px-3 text-[12px] font-medium transition-colors",
									selected
										? "text-foreground after:absolute after:inset-x-2 after:bottom-0 after:h-0.5 after:rounded-full after:bg-blue-600"
										: "text-muted-foreground hover:text-foreground",
								)}
							>
								<Icon className="size-4" aria-hidden="true" />
								{view.label}
							</button>
						);
					})}
				</div>
			</nav>

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
					{activeView === "overview" ? (
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
					) : null}

					{activeView === "overview" ? (
						<AdminGroup
							icon={Bot}
							title="Состояние агентного контура"
							description="Профессиональные агенты, модельные подключения и runtime-профили разделены. Здесь показаны только фактически зарегистрированные подключения."
						>
							<AgentAvailability
								providers={snapshot.providers}
								providersTruncated={snapshot.providersTruncated}
								runtimes={snapshot.runtimes}
								runtimesTruncated={snapshot.runtimesTruncated}
							/>
						</AdminGroup>
					) : null}

					{activeView === "hosts" ? (
						<>
							<AdminGroup
								icon={Server}
								title="Реестр хостов"
								description="Home и Primary — первые инфраструктурные узлы общего реестра. Agent Host-привязки загружаются cursor-страницами, чтобы список не зависел от будущего количества серверов."
							>
								<TrustedAgentAdmin />
							</AdminGroup>
							<AdminGroup
								icon={HardDrive}
								title="Home и Primary"
								description="Реальное состояние текущих storage-узлов и безопасные операции обслуживания без имитации доступности."
							>
								<StorageAdmin />
							</AdminGroup>
						</>
					) : null}

					{activeView === "agents" ? (
						<>
							<AdminGroup
								icon={Bot}
								title="Агенты строительного модуля"
								description="Активные профессиональные роли с собственными Agent Cards, инструментами, критериями завершения и версионируемыми системными инструкциями."
							>
								<ConstructionAgentAdmin />
							</AdminGroup>
							<AdminGroup
								icon={Activity}
								title="Runtime и модели"
								description="Инфраструктурные исполнители профессиональных агентов. MiMo/Codex остаются runtime-профилями и не подменяют роли сотрудников."
							>
								<AgentAvailability
									providers={snapshot.providers}
									providersTruncated={snapshot.providersTruncated}
									runtimes={snapshot.runtimes}
									runtimesTruncated={snapshot.runtimesTruncated}
								/>
							</AdminGroup>
						</>
					) : null}

					{activeView === "tasks" ? (
						<AdminGroup
							icon={Bot}
							title="Агентные задачи"
							description="Выберите одну задачу, чтобы наблюдать её сохранённый ход работы, диалог и управление в одном операционном Canvas."
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
							<Input
								type="search"
								aria-label="Поиск агентных задач"
								value={operationSearch}
								onChange={(event) => setOperationSearch(event.target.value)}
								placeholder="Найти по задаче, tenant, профилю или политике"
								className="mb-3 h-10 rounded-xl shadow-none"
							/>
							<AgentTaskWorkspace
								hasMore={snapshot.operationCursor !== null}
								loadingMore={loadingPage === "operations"}
								onLoadMore={() => void loadMore("operations")}
								onOperationChanged={() => load()}
								onSelect={setSelectedOperationKey}
								operations={filteredOperations}
								selectedKey={selectedOperationKey}
							/>
						</AdminGroup>
					) : null}

					{activeView === "clients" ? (
						<>
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
						</>
					) : null}

					{activeView === "models" ? (
						<PlatformModelsPanel
							models={snapshot.platformModels}
							onModelsChange={(updated) =>
								setSnapshot((s) =>
									s ? { ...s, platformModels: updated } : s,
								)
							}
						/>
					) : null}

					{activeView === "billing" ? <PlatformBillingPanel /> : null}

					{activeView === "audit" ? (
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
					) : null}
				</>
			) : null}
		</section>
	);
}

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
									runtime.startupStatus === "start_failed" ? "failed" : "ready"
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
				<Icon
					className="text-muted-foreground mt-0.5 size-5"
					aria-hidden="true"
				/>
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
							setDeveloperAccess(event.target.value as typeof developerAccess)
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

const PROVIDER_OPTIONS = [
	{ value: "openai", label: "OpenAI" },
	{ value: "anthropic", label: "Anthropic" },
	{ value: "qwen", label: "Qwen" },
	{ value: "mimo", label: "MiMo" },
	{ value: "custom", label: "Custom (OpenAI-compatible)" },
] as const;

function PlatformModelsPanel({
	models,
	onModelsChange,
}: {
	models: PlatformModel[];
	onModelsChange: (models: PlatformModel[]) => void;
}) {
	const [showForm, setShowForm] = useState(false);
	const [formBusy, setFormBusy] = useState(false);
	const [formError, setFormError] = useState<string | null>(null);
	const [formSuccess, setFormSuccess] = useState<string | null>(null);

	// Form state
	const [providerType, setProviderType] = useState("openai");
	const [providerName, setProviderName] = useState("");
	const [modelId, setModelId] = useState("");
	const [displayName, setDisplayName] = useState("");
	const [description, setDescription] = useState("");
	const [apiKey, setApiKey] = useState("");
	const [baseUrl, setBaseUrl] = useState("");
	const [autoPriority, setAutoPriority] = useState("50");

	const resetForm = () => {
		setProviderType("openai");
		setProviderName("");
		setModelId("");
		setDisplayName("");
		setDescription("");
		setApiKey("");
		setBaseUrl("");
		setAutoPriority("50");
		setFormError(null);
		setFormSuccess(null);
	};

	const handleCreate = async (event: FormEvent) => {
		event.preventDefault();
		setFormBusy(true);
		setFormError(null);
		setFormSuccess(null);
		try {
			const payload: PlatformModelCreate = {
				providerType,
				providerName: providerName || undefined,
				modelId,
				displayName,
				description: description || undefined,
				apiKey,
				baseUrl: providerType === "custom" ? baseUrl : undefined,
				autoPriority: Number(autoPriority) || 50,
			};
			const created = await createPlatformModel(payload);
			onModelsChange([created, ...models]);
			setFormSuccess(`Модель «${created.displayName}» добавлена.`);
			resetForm();
			setShowForm(false);
		} catch (err) {
			setFormError(
				err instanceof Error ? err.message : "Не удалось добавить модель.",
			);
		} finally {
			setFormBusy(false);
		}
	};

	return (
		<AdminGroup
			icon={Bot}
			title="Платформенные модели"
			description="Модели, доступные всем пользователям платформы. API-ключ хранится на уровне платформы."
		>
			<div className="mb-4 flex items-center gap-3">
				<Button
					type="button"
					variant="outline"
					size="sm"
					onClick={() => {
						setShowForm(!showForm);
						setFormError(null);
						setFormSuccess(null);
					}}
					className="rounded-lg shadow-none"
				>
					<Plus className="size-4" aria-hidden="true" />
					{showForm ? "Скрыть форму" : "Добавить модель"}
				</Button>
				{formSuccess ? (
					<span className="text-[12px] text-emerald-600">{formSuccess}</span>
				) : null}
			</div>

			{showForm ? (
				<form
					onSubmit={(e) => void handleCreate(e)}
					className="mb-6 space-y-3 rounded-2xl border bg-card p-4"
				>
					<h4 className="text-[13px] font-semibold">Новая модель</h4>
					<div className="grid gap-3 sm:grid-cols-2">
						<div className="space-y-1.5">
							<label className="text-[12px] font-medium text-muted-foreground">
								Тип провайдера
							</label>
							<select
								value={providerType}
								onChange={(e) => setProviderType(e.target.value)}
								className="h-10 w-full rounded-xl border bg-background px-3 text-[12px] shadow-none"
							>
								{PROVIDER_OPTIONS.map((opt) => (
									<option key={opt.value} value={opt.value}>
										{opt.label}
									</option>
								))}
							</select>
						</div>
						<LabeledInput
							label="Название провайдера"
							value={providerName}
							onChange={setProviderName}
							placeholder={providerType}
						/>
						<LabeledInput
							label="Model ID *"
							value={modelId}
							onChange={setModelId}
							placeholder="gpt-4o"
						/>
						<LabeledInput
							label="Отображаемое имя *"
							value={displayName}
							onChange={setDisplayName}
							placeholder="GPT-4o"
						/>
						<div className="space-y-1.5">
							<label className="text-[12px] font-medium text-muted-foreground">
								API ключ *
							</label>
							<Input
								type="password"
								value={apiKey}
								onChange={(e) => setApiKey(e.target.value)}
								placeholder="sk-..."
								className="h-10 rounded-xl text-[12px] shadow-none"
							/>
						</div>
						{providerType === "custom" ? (
							<LabeledInput
								label="Base URL *"
								value={baseUrl}
								onChange={setBaseUrl}
								placeholder="https://api.example.com/v1"
							/>
						) : null}
						<LabeledInput
							label="Приоритет (0–100)"
							value={autoPriority}
							onChange={setAutoPriority}
							inputMode="numeric"
							placeholder="50"
						/>
					</div>
					<div>
						<label className="text-[12px] font-medium text-muted-foreground">
							Описание
						</label>
						<textarea
							value={description}
							onChange={(e) => setDescription(e.target.value)}
							placeholder="Краткое описание модели"
							rows={2}
							className="mt-1 w-full rounded-xl border bg-background px-3 py-2 text-[12px] shadow-none resize-none"
						/>
					</div>
					{formError ? (
						<p className="text-[12px] text-destructive" role="alert">
							{formError}
						</p>
					) : null}
					<div className="flex gap-2">
						<Button
							type="submit"
							size="sm"
							disabled={formBusy || !modelId || !displayName || !apiKey}
							className="rounded-lg shadow-none"
						>
							{formBusy ? (
								<LoaderCircle className="size-4 animate-spin" />
							) : (
								<Plus className="size-4" />
							)}
							Добавить
						</Button>
						<Button
							type="button"
							variant="outline"
							size="sm"
							onClick={() => {
								setShowForm(false);
								resetForm();
							}}
							className="rounded-lg shadow-none"
						>
							Отмена
						</Button>
					</div>
				</form>
			) : null}

			{models.length ? (
				<div className="space-y-2">
					{models.map((model) => (
						<PlatformModelCard
							key={model.id}
							model={model}
							onUpdated={(updated) =>
								onModelsChange(
									models.map((m) => (m.id === updated.id ? updated : m)),
								)
							}
							onDeleted={(id) =>
								onModelsChange(models.filter((m) => m.id !== id))
							}
						/>
					))}
				</div>
			) : (
				<EmptyState text="Платформенные модели не добавлены." />
			)}
		</AdminGroup>
	);
}

function PlatformBillingPanel() {
	const [config, setConfig] = useState<BillingAdminConfig | null>(null);
	const [loadError, setLoadError] = useState<string | null>(null);
	const [busy, setBusy] = useState(false);
	const [failed, setFailed] = useState(false);
	const [message, setMessage] = useState<string | null>(null);
	const [enabled, setEnabled] = useState(false);
	const [mode, setMode] = useState<"test" | "demo">("demo");
	const [terminalKey, setTerminalKey] = useState("");
	const [password, setPassword] = useState("");
	const [notificationUrl, setNotificationUrl] = useState("");
	const [returnOrigin, setReturnOrigin] = useState("");
	const [receiptMode, setReceiptMode] = useState<"disabled" | "required">(
		"disabled",
	);
	const [verifySsl, setVerifySsl] = useState(true);
	const [taxation, setTaxation] = useState("");

	const load = useCallback(async () => {
		setLoadError(null);
		try {
			const next = await getAdminBillingConfig();
			setConfig(next);
			setEnabled(next.status === "configured" && next.source === "admin");
			if (next.mode === "test" || next.mode === "demo") setMode(next.mode);
			setReceiptMode(next.receiptMode ?? "disabled");
			setVerifySsl(next.verifySsl);
		} catch (error) {
			setLoadError(
				error instanceof Error
					? error.message
					: "Не удалось загрузить настройки оплаты.",
			);
		}
	}, []);

	useEffect(() => {
		void load();
	}, [load]);

	const submit = async (event: FormEvent) => {
		event.preventDefault();
		setBusy(true);
		setFailed(false);
		setMessage(null);
		try {
			const input: BillingAdminConfigUpdate = { enabled, mode };
			if (enabled) {
				input.terminalKey = terminalKey;
				input.password = password;
				input.notificationUrl = notificationUrl;
				input.returnOrigin = returnOrigin;
				input.receiptMode = receiptMode;
				input.taxation = taxation;
				input.verifySsl = verifySsl;
			}
			const next = await saveAdminBillingConfig(input);
			setConfig(next);
			setMessage(
				enabled
					? "Оплата подключена и сохранена."
					: "Оплата отключена.",
			);
			setTerminalKey("");
			setPassword("");
		} catch (error) {
			setFailed(true);
			setMessage(
				error instanceof Error
					? error.message
					: "Не удалось сохранить настройки оплаты.",
			);
		} finally {
			setBusy(false);
		}
	};

	const envManaged = config?.source === "env";

	return (
		<AdminGroup
			icon={CreditCard}
			title="Оплата · T‑Банк"
			description="DEMO и тестовый терминал настраиваются здесь. Рабочий (production) терминал включается только переменными окружения."
		>
			{loadError ? <StatusMessage failed message={loadError} /> : null}
			<StatusMessage failed={failed} message={message} />

			<div className="grid gap-3 rounded-2xl border bg-card p-4 sm:grid-cols-2">
				<div className="text-[12px] text-muted-foreground">
					Статус:{" "}
					<span className="font-semibold text-foreground">
						{config?.status === "configured"
							? "Подключено"
							: config?.status === "invalid"
								? "Требует проверки"
								: "Отключено"}
					</span>
				</div>
				<div className="text-[12px] text-muted-foreground">
					Источник:{" "}
					<span className="font-semibold text-foreground">
						{config?.source === "env"
							? "переменные окружения"
							: config?.source === "admin"
								? "админ-панель"
								: "не задан"}
					</span>
				</div>
				{config?.terminalFingerprint ? (
					<div className="text-[12px] text-muted-foreground">
						Терминал:{" "}
						<span className="font-mono font-semibold text-foreground">
							{config.terminalFingerprint}
						</span>
					</div>
				) : null}
				{config?.updatedAt ? (
					<div className="text-[12px] text-muted-foreground">
						Обновлено:{" "}
						<span className="font-semibold text-foreground">
							{new Date(config.updatedAt * 1_000).toLocaleString("ru-RU")}
						</span>
					</div>
				) : null}
			</div>

			{envManaged ? (
				<div className="mt-3 rounded-2xl border border-amber-500/30 bg-amber-500/[0.07] px-4 py-3 text-[12px] leading-5">
					Оплата управляется переменными окружения (KOLIBRI_V3_TBANK_*).
					Чтобы использовать админ-панель, отключите их.
				</div>
			) : (
				<form
					onSubmit={submit}
					className="mt-4 grid gap-3 sm:grid-cols-2"
					aria-label="Настройки оплаты"
				>
					<label className="flex items-center gap-2 text-[12px]">
						<input
							type="checkbox"
							checked={enabled}
							onChange={(event) => setEnabled(event.target.checked)}
							className="size-4"
						/>
						Оплата подключена
					</label>
					<label className="flex items-center gap-2 text-[12px]">
						Режим терминала
						<select
							value={mode}
							onChange={(event) =>
								setMode(event.target.value === "test" ? "test" : "demo")
							}
							className="h-9 rounded-lg border bg-card px-2 text-[12px]"
						>
							<option value="demo">DEMO (тесты банка)</option>
							<option value="test">Тестовый терминал</option>
						</select>
					</label>
					{enabled ? (
						<>
							<LabeledInput
								label="TerminalKey *"
								value={terminalKey}
								onChange={setTerminalKey}
								placeholder="Ключ терминала из кабинета"
							/>
							<label className="block text-[11px] font-medium">
								Password *
								<Input
									type="password"
									value={password}
									placeholder="Пароль терминала из кабинета"
									onChange={(event) => setPassword(event.target.value)}
									className="mt-1.5 h-9 rounded-lg text-[12px] shadow-none"
									autoComplete="new-password"
								/>
							</label>
							<LabeledInput
								label="NotificationURL"
								value={notificationUrl}
								onChange={setNotificationUrl}
								placeholder="http://127.0.0.1:3103/api/v3/billing/tbank/notifications"
							/>
							<LabeledInput
								label="Return origin"
								value={returnOrigin}
								onChange={setReturnOrigin}
								placeholder="http://127.0.0.1:3103"
							/>
							<label className="flex items-center gap-2 text-[12px]">
								Кассовый чек
								<select
									value={receiptMode}
									onChange={(event) =>
										setReceiptMode(
											event.target.value === "required"
												? "required"
												: "disabled",
										)
									}
									className="h-9 rounded-lg border bg-card px-2 text-[12px]"
								>
									<option value="disabled">Не подключён</option>
									<option value="required">Требуется</option>
								</select>
							</label>
							<LabeledInput
								label="СНО (для чека)"
								value={taxation}
								onChange={setTaxation}
								placeholder="osn / usn_income / …"
							/>
							<label className="flex items-center gap-2 text-[12px]">
								<input
									type="checkbox"
									checked={verifySsl}
									onChange={(event) => setVerifySsl(event.target.checked)}
									className="size-4"
								/>
								Проверять SSL-сертификат банка
								<span className="text-muted-foreground">
									(отключите только для локальной разработки)
								</span>
							</label>
						</>
					) : null}
					<div className="sm:col-span-2">
						<Button
							type="submit"
							disabled={busy}
							className="min-h-10 rounded-xl"
						>
							{busy ? (
								<LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
							) : (
								<Check className="size-4" aria-hidden="true" />
							)}
							Сохранить настройки оплаты
						</Button>
					</div>
				</form>
			)}
		</AdminGroup>
	);
}

function PlatformModelCard({
	model,
	onUpdated,
	onDeleted,
}: {
	model: PlatformModel;
	onUpdated: (model: PlatformModel) => void;
	onDeleted: (id: string) => void;
}) {
	const [busy, setBusy] = useState<"test" | "toggle" | "delete" | null>(null);
	const [message, setMessage] = useState<string | null>(null);
	const [failed, setFailed] = useState(false);

	const runTest = async () => {
		setBusy("test");
		setMessage(null);
		setFailed(false);
		try {
			const result = await testPlatformModel(model.id);
			setMessage(result.message);
			setFailed(result.status !== "connected");
			onUpdated({ ...model, lastTestStatus: result.status, lastTestedAt: new Date().toISOString() });
		} catch (err) {
			setMessage(err instanceof Error ? err.message : "Ошибка тестирования.");
			setFailed(true);
		} finally {
			setBusy(null);
		}
	};

	const toggleEnabled = async () => {
		setBusy("toggle");
		setMessage(null);
		setFailed(false);
		try {
			const updated = await updatePlatformModel(model.id, {
				isEnabled: !model.isEnabled,
			});
			onUpdated(updated);
		} catch (err) {
			setMessage(err instanceof Error ? err.message : "Ошибка обновления.");
			setFailed(true);
		} finally {
			setBusy(null);
		}
	};

	const remove = async () => {
		setBusy("delete");
		setMessage(null);
		setFailed(false);
		try {
			await deletePlatformModel(model.id);
			onDeleted(model.id);
		} catch (err) {
			setMessage(err instanceof Error ? err.message : "Ошибка удаления.");
			setFailed(true);
			setBusy(null);
		}
	};

	const statusTone =
		model.lastTestStatus === "connected"
			? "ready"
			: model.lastTestStatus === "failed"
				? "failed"
				: "neutral";

	return (
		<article className="rounded-2xl border bg-card p-4">
			<div className="flex items-start justify-between gap-3">
				<div className="min-w-0 flex-1">
					<div className="flex items-center gap-2">
						<p className="truncate text-[13px] font-semibold">
							{model.displayName}
						</p>
						<AgentStateBadge
							state={model.isEnabled ? "ready" : "neutral"}
							label={model.isEnabled ? "Включена" : "Отключена"}
						/>
						<AgentStateBadge state={statusTone} label={model.providerType} />
					</div>
					<p className="text-muted-foreground mt-1 truncate text-[11px]">
						{model.modelId}
						{model.baseUrl ? ` · ${model.baseUrl}` : ""}
						{` · приоритет ${model.autoPriority}`}
					</p>
					{model.description ? (
						<p className="text-muted-foreground mt-1 text-[11px]">
							{model.description}
						</p>
					) : null}
					{model.lastTestedAt ? (
						<p className="text-muted-foreground mt-1 text-[10px]">
							Последний тест:{" "}
							{new Date(model.lastTestedAt).toLocaleString("ru-RU")} —{" "}
							{model.lastTestStatus === "connected"
								? "успешно"
								: model.lastTestStatus ?? "нет данных"}
						</p>
					) : null}
				</div>
				<div className="flex shrink-0 items-center gap-1">
					<Button
						type="button"
						variant="outline"
						size="sm"
						disabled={busy !== null}
						onClick={() => void runTest()}
						className="rounded-lg shadow-none"
						title="Тестировать подключение"
					>
						{busy === "test" ? (
							<LoaderCircle className="size-4 animate-spin" />
						) : (
							<TestTube2 className="size-4" />
						)}
					</Button>
					<Button
						type="button"
						variant="outline"
						size="sm"
						disabled={busy !== null}
						onClick={() => void toggleEnabled()}
						className="rounded-lg shadow-none"
						title={model.isEnabled ? "Отключить" : "Включить"}
					>
						{busy === "toggle" ? (
							<LoaderCircle className="size-4 animate-spin" />
						) : (
							<Check
								className={cn(
									"size-4",
									!model.isEnabled && "opacity-30",
								)}
							/>
						)}
					</Button>
					<Button
						type="button"
						variant="outline"
						size="sm"
						disabled={busy !== null}
						onClick={() => void remove()}
						className="rounded-lg shadow-none text-destructive hover:text-destructive"
						title="Удалить"
					>
						{busy === "delete" ? (
							<LoaderCircle className="size-4 animate-spin" />
						) : (
							<Trash2 className="size-4" />
						)}
					</Button>
				</div>
			</div>
			<StatusMessage failed={failed} message={message} />
		</article>
	);
}
