"use client";

import {
	Bot,
	CheckCircle2,
	ChevronRight,
	LoaderCircle,
	RefreshCw,
	Save,
	Search,
	Wrench,
} from "lucide-react";
import {
	useCallback,
	useDeferredValue,
	useEffect,
	useMemo,
	useState,
} from "react";
import {
	AdminEmptyState,
	AdminLoadMoreButton,
	AdminStatusBadge,
} from "@/components/kolibri-shell/admin/admin-primitives";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
	getConstructionAgentsPage,
	updateConstructionAgent,
	type ConstructionAgentCard,
} from "@/lib/platform-admin/construction-agents-client";
import { cn } from "@/lib/utils";

const mergeAgents = (
	current: ConstructionAgentCard[],
	incoming: ConstructionAgentCard[],
) => {
	const merged = new Map(current.map((agent) => [agent.agentId, agent]));
	for (const agent of incoming) merged.set(agent.agentId, agent);
	return [...merged.values()].sort((left, right) =>
		left.displayName.localeCompare(right.displayName, "ru"),
	);
};

export function ConstructionAgentAdmin() {
	const [agents, setAgents] = useState<ConstructionAgentCard[]>([]);
	const [cursor, setCursor] = useState<string | null>(null);
	const [selectedId, setSelectedId] = useState<string | null>(null);
	const [search, setSearch] = useState("");
	const deferredSearch = useDeferredValue(search);
	const [loading, setLoading] = useState(true);
	const [loadingMore, setLoadingMore] = useState(false);
	const [error, setError] = useState<string | null>(null);

	const load = useCallback(
		async (signal?: AbortSignal) => {
			setLoading(true);
			try {
				const page = await getConstructionAgentsPage({
					query: deferredSearch,
					signal,
				});
				setAgents(page.items);
				setCursor(page.nextCursor);
				setSelectedId((current) =>
					page.items.some((agent) => agent.agentId === current)
						? current
						: (page.items[0]?.agentId ?? null),
				);
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
						: "Реестр профессиональных агентов недоступен.",
				);
			} finally {
				if (!signal?.aborted) setLoading(false);
			}
		},
		[deferredSearch],
	);

	useEffect(() => {
		const controller = new AbortController();
		void load(controller.signal);
		return () => controller.abort();
	}, [load]);

	const selectedAgent = useMemo(
		() => agents.find((agent) => agent.agentId === selectedId) ?? null,
		[agents, selectedId],
	);

	const loadMore = async () => {
		if (!cursor || loadingMore) return;
		setLoadingMore(true);
		try {
			const page = await getConstructionAgentsPage({
				cursor,
				query: deferredSearch,
			});
			setAgents((current) => mergeAgents(current, page.items));
			setCursor(page.nextCursor);
			setError(null);
		} catch (requestError) {
			setError(
				requestError instanceof Error
					? requestError.message
					: "Следующая страница агентов не загружена.",
			);
		} finally {
			setLoadingMore(false);
		}
	};

	const replaceAgent = (agent: ConstructionAgentCard) => {
		setAgents((current) =>
			current.map((item) => (item.agentId === agent.agentId ? agent : item)),
		);
	};

	return (
		<div data-slot="construction-agent-admin">
			<div className="rounded-2xl border bg-card p-4">
				<div className="flex flex-wrap items-start justify-between gap-4">
					<div className="max-w-3xl">
						<div className="flex items-center gap-2">
							<Bot
								className="text-muted-foreground size-5"
								aria-hidden="true"
							/>
							<h4 className="text-[14px] font-semibold">
								Профессиональные агенты
							</h4>
							<span className="rounded-full border px-2 py-0.5 text-[10px] font-medium">
								construction
							</span>
						</div>
						<p className="text-muted-foreground mt-2 text-[12px] leading-5">
							Это рабочие Agent Cards строительного модуля — роли, инструменты,
							ограничения и системные инструкции. MiMo/Codex ниже по стеку
							являются runtime-профилями и не заменяют профессиональные роли.
						</p>
					</div>
					<Button
						type="button"
						variant="outline"
						size="sm"
						disabled={loading}
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
				<div className="relative mt-4">
					<Search
						className="text-muted-foreground pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2"
						aria-hidden="true"
					/>
					<Input
						type="search"
						aria-label="Поиск профессиональных агентов"
						value={search}
						onChange={(event) => setSearch(event.target.value)}
						placeholder="Роль, название или Agent ID"
						className="h-10 rounded-xl pl-9 shadow-none"
					/>
				</div>
			</div>

			{error ? (
				<p
					className="border-destructive/30 text-destructive mt-4 rounded-xl border px-3 py-2 text-[11px]"
					role="alert"
				>
					{error}
				</p>
			) : null}

			{loading && !agents.length ? (
				<div className="text-muted-foreground mt-4 flex items-center gap-2 rounded-2xl border p-4 text-[12px]">
					<LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
					Читаем Agent Cards из строительного модуля
				</div>
			) : null}

			{!loading && !agents.length ? (
				<AdminEmptyState text="Профессиональные агенты по этому запросу не найдены." />
			) : null}

			{agents.length ? (
				<div className="mt-4 grid min-h-[540px] overflow-hidden rounded-2xl border bg-card lg:grid-cols-[minmax(280px,0.72fr)_minmax(0,1.35fr)]">
					<div className="border-b lg:border-r lg:border-b-0">
						<div className="text-muted-foreground flex items-center justify-between border-b px-4 py-3 text-[11px]">
							<span>Агенты</span>
							<span>{agents.length}</span>
						</div>
						<div className="max-h-[600px] overflow-y-auto p-2">
							{agents.map((agent) => (
								<button
									type="button"
									key={agent.agentId}
									onClick={() => setSelectedId(agent.agentId)}
									className={cn(
										"flex w-full items-center gap-3 rounded-xl px-3 py-3 text-left transition-colors",
										selectedId === agent.agentId
											? "bg-blue-500/10 text-blue-950 dark:text-blue-100"
											: "hover:bg-muted/70",
									)}
								>
									<span className="flex size-9 shrink-0 items-center justify-center rounded-xl border bg-background">
										<Bot className="size-4" aria-hidden="true" />
									</span>
									<span className="min-w-0 flex-1">
										<span className="block truncate text-[12px] font-semibold">
											{agent.displayName}
										</span>
										<span className="text-muted-foreground mt-0.5 block truncate text-[10px]">
											{agent.role} · {agent.modelProfile}
										</span>
									</span>
									<AdminStatusBadge label="Активен" tone="ready" />
									<ChevronRight
										className="text-muted-foreground size-4 shrink-0"
										aria-hidden="true"
									/>
								</button>
							))}
						</div>
						<AdminLoadMoreButton
							cursor={cursor}
							loading={loadingMore}
							disabled={loadingMore}
							onClick={() => void loadMore()}
							className="m-3"
						>
							Ещё агентов
						</AdminLoadMoreButton>
					</div>
					{selectedAgent ? (
						<ConstructionAgentEditor
							key={`${selectedAgent.agentId}:${selectedAgent.configurationRevision}`}
							agent={selectedAgent}
							onUpdated={replaceAgent}
						/>
					) : null}
				</div>
			) : null}
		</div>
	);
}

function ConstructionAgentEditor({
	agent,
	onUpdated,
}: {
	agent: ConstructionAgentCard;
	onUpdated: (agent: ConstructionAgentCard) => void;
}) {
	const [systemPrompt, setSystemPrompt] = useState(agent.systemPrompt);
	const [modelProfile, setModelProfile] = useState(agent.modelProfile);
	const [busy, setBusy] = useState(false);
	const [message, setMessage] = useState<string | null>(null);
	const [failed, setFailed] = useState(false);
	const changed =
		systemPrompt.trim() !== agent.systemPrompt ||
		modelProfile.trim() !== agent.modelProfile;

	const save = async () => {
		if (!changed || busy) return;
		setBusy(true);
		setMessage(null);
		try {
			const updated = await updateConstructionAgent(agent.agentId, {
				revision: agent.configurationRevision,
				systemPrompt: systemPrompt.trim(),
				modelProfile: modelProfile.trim(),
			});
			onUpdated(updated);
			setSystemPrompt(updated.systemPrompt);
			setModelProfile(updated.modelProfile);
			setFailed(false);
			setMessage(
				`Инструкции сохранены как ревизия ${updated.configurationRevision}.`,
			);
		} catch (requestError) {
			setFailed(true);
			setMessage(
				requestError instanceof Error
					? requestError.message
					: "Инструкции агента не сохранены.",
			);
		} finally {
			setBusy(false);
		}
	};

	return (
		<div className="min-w-0 p-5" data-agent-card={agent.agentId}>
			<div className="flex flex-wrap items-start justify-between gap-3">
				<div className="min-w-0">
					<h5 className="text-lg font-semibold tracking-[-0.02em]">
						{agent.displayName}
					</h5>
					<p className="text-muted-foreground mt-1 break-all font-mono text-[10px]">
						{agent.agentId} · card v{agent.cardVersion} · config r
						{agent.configurationRevision}
					</p>
				</div>
				<AdminStatusBadge
					label={agent.source === "configured" ? "Настроен" : "Базовая версия"}
					tone={agent.source === "configured" ? "running" : "neutral"}
				/>
			</div>

			<div className="mt-5 grid gap-3 sm:grid-cols-2">
				<label className="text-[11px] font-medium">
					Роль
					<Input
						value={agent.role}
						disabled
						className="mt-1.5 h-9 rounded-lg text-[12px] shadow-none"
					/>
				</label>
				<label className="text-[11px] font-medium">
					Профиль модели
					<Input
						value={modelProfile}
						onChange={(event) => setModelProfile(event.target.value)}
						className="mt-1.5 h-9 rounded-lg text-[12px] shadow-none"
					/>
				</label>
			</div>

			<label className="mt-4 block text-[11px] font-medium">
				Системная инструкция
				<textarea
					value={systemPrompt}
					onChange={(event) => setSystemPrompt(event.target.value)}
					rows={11}
					spellCheck
					className="border-input bg-background placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-ring/50 mt-1.5 w-full resize-y rounded-xl border px-3 py-2 text-[12px] leading-5 outline-none focus-visible:ring-[3px]"
				/>
			</label>

			<div className="mt-4 flex flex-wrap items-center justify-between gap-3">
				<p className="text-muted-foreground max-w-lg text-[10px] leading-4">
					Сохранение создаёт новую неизменяемую ревизию. Новые задания получают
					актуальную инструкцию; выполненные события и результаты не
					переписываются.
				</p>
				<Button
					type="button"
					size="sm"
					disabled={!changed || busy || systemPrompt.trim().length < 20}
					onClick={() => void save()}
					className="rounded-lg shadow-none"
				>
					{busy ? (
						<LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
					) : (
						<Save className="size-4" aria-hidden="true" />
					)}
					Сохранить ревизию
				</Button>
			</div>
			{message ? (
				<p
					className={cn(
						"mt-3 text-[11px]",
						failed
							? "text-destructive"
							: "text-emerald-700 dark:text-emerald-300",
					)}
					role={failed ? "alert" : "status"}
				>
					{message}
				</p>
			) : null}

			<div className="mt-6 grid gap-4 xl:grid-cols-2">
				<AgentDetailList
					icon={Wrench}
					title="Разрешённые инструменты"
					items={agent.allowedTools}
					empty="Инструменты не назначены"
				/>
				<AgentDetailList
					icon={CheckCircle2}
					title="Критерии завершения"
					items={agent.completionCriteria}
					empty="Критерии не заданы"
				/>
			</div>
		</div>
	);
}

function AgentDetailList({
	empty,
	icon: Icon,
	items,
	title,
}: {
	empty: string;
	icon: typeof Wrench;
	items: string[];
	title: string;
}) {
	return (
		<section className="rounded-xl border p-3">
			<div className="flex items-center gap-2">
				<Icon className="text-muted-foreground size-4" aria-hidden="true" />
				<h6 className="text-[11px] font-semibold">{title}</h6>
			</div>
			{items.length ? (
				<ul className="mt-2 space-y-1.5">
					{items.map((item) => (
						<li
							key={item}
							className="text-muted-foreground text-[10px] leading-4"
						>
							{item}
						</li>
					))}
				</ul>
			) : (
				<p className="text-muted-foreground mt-2 text-[10px]">{empty}</p>
			)}
		</section>
	);
}
