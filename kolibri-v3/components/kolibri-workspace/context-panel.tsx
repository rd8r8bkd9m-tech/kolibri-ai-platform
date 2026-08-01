"use client";

import {
	AlertTriangle,
	CheckCircle2,
	CircleDot,
	Database,
	Files as FilesIcon,
	FolderOpen,
	Globe2,
	LockKeyhole,
	type LucideIcon,
	Paperclip,
	ShieldCheck,
	SquareTerminal,
	X,
} from "lucide-react";
import type { ComponentType } from "react";

import { Button } from "@/components/ui/button";
import {
	Tooltip,
	TooltipContent,
	TooltipProvider,
	TooltipTrigger,
} from "@/components/ui/tooltip";

export const CONTEXT_PANEL_TABS = [
	{ id: "review", label: "Проверка", icon: ShieldCheck },
	{ id: "terminal", label: "Терминал", icon: SquareTerminal },
	{ id: "browser", label: "Браузер", icon: Globe2 },
	{ id: "files", label: "Файлы", icon: FilesIcon },
] as const satisfies ReadonlyArray<{
	id: string;
	label: string;
	icon: LucideIcon;
}>;

export type ContextPanelMode = (typeof CONTEXT_PANEL_TABS)[number]["id"];

export interface ContextPanelProps {
	embedded?: boolean;
	projectName?: string;
	mode?: ContextPanelMode;
	onClose?: () => void;
	onOpenSettings?: () => void;
}

type EmptyStateProps = {
	action?: {
		label: string;
		onClick: () => void;
	};
	icon: LucideIcon;
	title: string;
	description: string;
	detail?: string;
};

function isContextPanelMode(value: unknown): value is ContextPanelMode {
	return CONTEXT_PANEL_TABS.some((tab) => tab.id === value);
}

function CloseButton({ onClose }: { onClose: () => void }) {
	return (
		<Tooltip>
			<TooltipTrigger asChild>
				<Button
					type="button"
					variant="ghost"
					size="icon-sm"
					onClick={onClose}
					className="text-muted-foreground hover:text-foreground"
				>
					<X aria-hidden="true" />
					<span className="sr-only">Закрыть панель инструментов</span>
				</Button>
			</TooltipTrigger>
			<TooltipContent side="bottom" sideOffset={6}>
				Закрыть панель
			</TooltipContent>
		</Tooltip>
	);
}

function EmptyState({
	action,
	icon: Icon,
	title,
	description,
	detail,
}: EmptyStateProps) {
	return (
		<div className="flex min-h-72 flex-col items-center justify-center px-5 py-10 text-center">
			<span className="border-border bg-muted/45 text-muted-foreground mb-4 grid size-11 place-items-center rounded-xl border">
				<Icon className="size-5" aria-hidden="true" />
			</span>
			<h3 className="text-sm font-semibold">{title}</h3>
			<p className="text-muted-foreground mt-1.5 max-w-xs text-xs leading-relaxed">
				{description}
			</p>
			{detail ? (
				<p className="border-border bg-muted/20 text-muted-foreground mt-4 max-w-xs rounded-lg border px-3 py-2.5 text-[11px] leading-relaxed">
					{detail}
				</p>
			) : null}
			{action ? (
				<Button
					type="button"
					variant="outline"
					size="sm"
					className="mt-4 rounded-lg shadow-none"
					onClick={action.onClick}
				>
					{action.label}
				</Button>
			) : null}
		</div>
	);
}

type TruthKind = {
	id: "facts" | "assumptions" | "decisions";
	label: string;
	emptyLabel: string;
	description: string;
	icon: LucideIcon;
};

const TRUTH_KINDS: readonly TruthKind[] = [
	{
		id: "facts",
		label: "Факты",
		emptyLabel: "Подтверждённых фактов нет",
		description: "Появятся только данные с источником и временем проверки.",
		icon: Database,
	},
	{
		id: "assumptions",
		label: "Допущения",
		emptyLabel: "Допущения не зафиксированы",
		description: "Каждое допущение будет помечено с основанием и влиянием.",
		icon: CircleDot,
	},
	{
		id: "decisions",
		label: "Решения",
		emptyLabel: "Утверждённых решений нет",
		description: "Предложения не считаются решениями без явного утверждения.",
		icon: CheckCircle2,
	},
];

function ReviewPanel() {
	return (
		<div>
			<section
				className="border-border/80 border-b px-4 py-4"
				aria-labelledby="version-state-title"
			>
				<div className="flex items-start justify-between gap-3">
					<div>
						<p id="version-state-title" className="text-xs font-semibold">
							Состояние версии
						</p>
						<p className="text-muted-foreground mt-0.5 text-[11px]">
							Данные проекта не подключены
						</p>
					</div>
					<span className="text-muted-foreground text-[10px] font-medium whitespace-nowrap">
						Нет версии
					</span>
				</div>
				<dl className="mt-4 grid grid-cols-[1fr_auto] gap-x-4 gap-y-2 text-xs">
					<dt className="text-muted-foreground">Входные данные</dt>
					<dd className="font-medium">—</dd>
					<dt className="text-muted-foreground">Последняя проверка</dt>
					<dd className="font-medium">—</dd>
					<dt className="text-muted-foreground">Доказательства</dt>
					<dd className="font-medium tabular-nums">0</dd>
					<dt className="text-muted-foreground">Выпуск</dt>
					<dd className="font-medium">Недоступен</dd>
				</dl>
			</section>

			<section
				className="border-border/80 border-b px-4 py-3.5"
				aria-labelledby="stale-policy-title"
			>
				<div className="flex items-start gap-2.5">
					<AlertTriangle
						className="text-muted-foreground mt-0.5 size-4 shrink-0"
						aria-hidden="true"
					/>
					<div>
						<h3 id="stale-policy-title" className="text-xs font-semibold">
							Правило выпуска
						</h3>
						<p className="text-muted-foreground mt-1 text-[11px] leading-relaxed">
							Изменение входных данных требует повторной проверки зависимых
							результатов.
						</p>
					</div>
				</div>
			</section>

			<section aria-labelledby="truth-register-title">
				<div className="border-border/80 flex items-center justify-between gap-2 border-b px-4 py-3">
					<h3 id="truth-register-title" className="text-xs font-semibold">
						Реестр контекста
					</h3>
					<span className="text-muted-foreground text-[10px]">Пустой</span>
				</div>
				<div className="divide-border divide-y">
					{TRUTH_KINDS.map(
						({ id, label, emptyLabel, description, icon: Icon }) => (
							<section
								key={id}
								data-truth-kind={id}
								className="flex items-start gap-2.5 px-4 py-3"
								aria-labelledby={`truth-kind-${id}`}
							>
								<span className="text-muted-foreground mt-0.5 grid size-6 shrink-0 place-items-center">
									<Icon className="size-3.5" aria-hidden="true" />
								</span>
								<div className="min-w-0">
									<h4 id={`truth-kind-${id}`} className="text-xs font-semibold">
										{label}
									</h4>
									<p className="mt-0.5 text-[11px] font-medium">{emptyLabel}</p>
									<p className="text-muted-foreground mt-0.5 text-[10px] leading-relaxed">
										{description}
									</p>
								</div>
							</section>
						),
					)}
				</div>
			</section>

			<section
				className="border-border/80 flex items-start gap-2.5 border-t px-4 py-4"
				aria-labelledby="evidence-empty-title"
			>
				<Paperclip
					className="text-muted-foreground mt-0.5 size-4 shrink-0"
					aria-hidden="true"
				/>
				<div>
					<h3 id="evidence-empty-title" className="text-xs font-medium">
						Доказательства не приложены
					</h3>
					<p className="text-muted-foreground mt-1 text-[10px] leading-relaxed">
						Источники и результаты проверки появятся после загрузки данных.
					</p>
				</div>
			</section>
		</div>
	);
}

function TerminalPanel() {
	return (
		<section
			className="flex h-full min-h-0 flex-col"
			aria-labelledby="terminal-title"
		>
			<div className="border-border/80 bg-[#111214] border-b px-4 py-3 text-[#f4f4f5]">
				<h3 id="terminal-title" className="font-mono text-xs font-medium">
					Терминал проекта
				</h3>
				<p className="mt-1 font-mono text-[10px] text-[#a1a1aa]">
					Сессия запускается только серверным runtime
				</p>
			</div>

			<div className="flex min-h-0 flex-1 items-center justify-center bg-[#111214] px-6 text-center">
				<div className="max-w-sm font-mono">
					<SquareTerminal
						className="mx-auto size-5 text-[#71717a]"
						aria-hidden="true"
					/>
					<p className="mt-3 text-xs font-medium text-[#f4f4f5]">
						Нет активной терминальной сессии
					</p>
					<p className="mt-1 text-[10px] leading-4 text-[#a1a1aa]">
						Когда агент откроет проверяемую сессию для этого проекта,
						вывод появится здесь в реальном времени.
					</p>
				</div>
			</div>
		</section>
	);
}

function BrowserPanel({ onOpenSettings }: { onOpenSettings?: () => void }) {
	return (
		<section
			className="flex h-full min-h-0 flex-col"
			aria-labelledby="browser-view-title"
		>
			<h2 id="browser-view-title" className="sr-only">
				Браузер маркетплейсов
			</h2>
			<header className="border-border/70 bg-muted/10 flex h-12 shrink-0 items-center gap-1 border-b px-2">
				<div className="border-border bg-background flex h-9 min-w-0 flex-1 items-center gap-2 rounded-xl border px-3">
					<LockKeyhole
						className="text-muted-foreground size-3 shrink-0"
						aria-hidden="true"
					/>
					<span className="min-w-0 truncate text-xs">
						kolibri://marketplaces
					</span>
				</div>
			</header>

			<div
				className="flex min-h-0 flex-1 flex-col overflow-y-auto"
				role="status"
			>
				<div className="my-auto">
					<EmptyState
						icon={Globe2}
						title="Подключения маркетплейсов не настроены"
						description="После подключения в личном кабинете здесь появятся предложения только из разрешённых источников."
						detail="Kolibri не показывает примерные цены и не добавляет позиции в проект без полученных данных."
						action={
							onOpenSettings
								? {
										label: "Открыть личный кабинет",
										onClick: onOpenSettings,
									}
								: undefined
						}
					/>
				</div>
				<footer className="border-border/70 text-muted-foreground flex min-h-9 shrink-0 items-center border-t px-4 text-[10px]">
					Нет активных подключений
				</footer>
			</div>
		</section>
	);
}

function FilesPanel() {
	return (
		<div className="p-3 sm:p-4">
			<section
				className="border-border bg-card overflow-hidden rounded-xl border"
				aria-labelledby="context-files-empty-title"
			>
				<header className="border-border/70 flex items-center justify-between border-b px-3.5 py-3">
					<div>
						<h3 className="text-xs font-semibold">Файлы контекста</h3>
						<p className="text-muted-foreground mt-0.5 text-[10px]">
							Вложения и версии
						</p>
					</div>
					<span className="bg-muted text-muted-foreground rounded-full px-2 py-1 text-[10px] tabular-nums">
						0
					</span>
				</header>
				<div className="border-border/70 text-muted-foreground grid grid-cols-[1fr_auto] border-b px-3.5 py-2 text-[10px] font-medium">
					<span>Имя</span>
					<span>Версия</span>
				</div>
				<EmptyState
					icon={FolderOpen}
					title="Файлы не прикреплены"
					description="Загруженные пользователем файлы и созданные артефакты появятся здесь с точной версией."
					detail="Пустое состояние не означает, что файлы проекта были удалены или обработаны."
				/>
				<span id="context-files-empty-title" className="sr-only">
					Пустое состояние файлов
				</span>
			</section>
		</div>
	);
}

const PANEL_CONTENT: Record<ContextPanelMode, ComponentType> = {
	review: ReviewPanel,
	terminal: TerminalPanel,
	browser: BrowserPanel,
	files: FilesPanel,
};

export function ContextPanel({
	embedded = false,
	projectName,
	mode = "review",
	onClose,
	onOpenSettings,
}: ContextPanelProps) {
	const activeTab = isContextPanelMode(mode) ? mode : "review";
	const projectLabel = projectName?.trim() || "Проект не выбран";
	const activeDefinition =
		CONTEXT_PANEL_TABS.find((tab) => tab.id === activeTab) ??
		CONTEXT_PANEL_TABS[0];
	const PanelContent = PANEL_CONTENT[activeTab];

	return (
		<TooltipProvider delayDuration={300}>
			<aside
				data-testid="context-panel"
				data-context-mode={activeTab}
				className="bg-background flex h-full min-h-0 min-w-0 flex-col overflow-hidden"
				aria-label="Панель инструментов проекта"
			>
				{!embedded ? (
					<header className="border-border/80 flex h-11 shrink-0 items-center justify-between gap-3 border-b px-3">
						<div className="min-w-0">
							<h2 className="truncate text-sm font-semibold">
								{activeDefinition.label}
							</h2>
							<p className="text-muted-foreground truncate text-[11px]">
								{projectLabel}
							</p>
						</div>
						{onClose ? <CloseButton onClose={onClose} /> : null}
					</header>
				) : null}

				<div
					role="region"
					aria-label={activeDefinition.label}
					className="min-h-0 flex-1 overflow-y-auto outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
				>
					{activeTab === "browser" ? (
						<BrowserPanel onOpenSettings={onOpenSettings} />
					) : (
						<PanelContent />
					)}
				</div>
			</aside>
		</TooltipProvider>
	);
}
