"use client";

import { Command } from "cmdk";
import {
	FileText,
	FolderKanban,
	Globe2,
	LibraryBig,
	PanelLeft,
	PanelRight,
	Search,
	Settings,
	ShieldCheck,
	SquarePen,
	SquareTerminal,
	type LucideIcon,
} from "lucide-react";
import type { ReactNode } from "react";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import type { WorkspaceFile, WorkspaceProject } from "@/lib/workspace-types";
import { cn } from "@/lib/utils";

export type WorkspaceCommandThread = {
	id: string;
	title?: string;
};

type WorkspaceCommandPaletteProps = {
	contextPanelOpen: boolean;
	files: readonly WorkspaceFile[];
	navigationOpen: boolean;
	onNewTask: () => void;
	onOpenBrowser: () => void;
	onOpenDocuments: () => void;
	onOpenProfile: () => void;
	onOpenProjects: () => void;
	onOpenReferences: () => void;
	onOpenReview: () => void;
	onOpenTerminal: () => void;
	onOpenChange: (open: boolean) => void;
	onSelectFile: (file: WorkspaceFile) => void;
	onSelectProject: (project: WorkspaceProject) => void;
	onSelectThread: (threadId: string) => void;
	onToggleContextPanel: () => void;
	onToggleNavigation: () => void;
	open: boolean;
	projects: readonly WorkspaceProject[];
	threads: readonly WorkspaceCommandThread[];
};

export function WorkspaceCommandPalette({
	contextPanelOpen,
	files,
	navigationOpen,
	onNewTask,
	onOpenBrowser,
	onOpenChange,
	onOpenDocuments,
	onOpenProfile,
	onOpenProjects,
	onOpenReferences,
	onOpenReview,
	onOpenTerminal,
	onSelectFile,
	onSelectProject,
	onSelectThread,
	onToggleContextPanel,
	onToggleNavigation,
	open,
	projects,
	threads,
}: WorkspaceCommandPaletteProps) {
	const run = (action: () => void) => {
		onOpenChange(false);
		action();
	};

	return (
		<Dialog open={open} onOpenChange={onOpenChange}>
			<DialogContent
				showCloseButton={false}
				className="top-[18vh] w-[min(42rem,calc(100vw-2rem))] max-w-none translate-y-0 gap-0 overflow-hidden rounded-2xl border p-0 shadow-2xl data-[state=closed]:slide-out-to-top-2 data-[state=open]:slide-in-from-top-2"
			>
				<DialogTitle className="sr-only">Команды и поиск</DialogTitle>
				<Command
					label="Команды и поиск по рабочему пространству"
					className="bg-popover text-popover-foreground flex max-h-[min(32rem,70vh)] min-h-0 flex-col"
				>
					<div className="border-border/75 flex h-12 shrink-0 items-center gap-2.5 border-b px-4">
						<Search
							aria-hidden="true"
							className="text-muted-foreground size-4 shrink-0"
						/>
						<Command.Input
							autoFocus
							placeholder="Найти команду, диалог, проект или документ…"
							className="placeholder:text-muted-foreground h-full min-w-0 flex-1 bg-transparent text-sm outline-none"
						/>
						<kbd className="bg-muted text-muted-foreground rounded-md px-1.5 py-1 font-sans text-[10px] leading-none">
							Esc
						</kbd>
					</div>

					<Command.List className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-2">
						<Command.Empty className="text-muted-foreground px-3 py-10 text-center text-sm">
							Ничего не найдено
						</Command.Empty>

						<PaletteGroup heading="Действия">
							<PaletteItem
								icon={SquarePen}
								label="Новая задача"
								keywords="создать диалог чат"
								onSelect={() => run(onNewTask)}
							/>
							<PaletteItem
								icon={FolderKanban}
								label="Открыть проекты"
								keywords="объекты задачи"
								onSelect={() => run(onOpenProjects)}
							/>
							<PaletteItem
								icon={FileText}
								label="Открыть документы"
								keywords="файлы сметы договоры"
								onSelect={() => run(onOpenDocuments)}
							/>
							<PaletteItem
								icon={LibraryBig}
								label="Открыть справочники"
								keywords="цены материалы работы"
								onSelect={() => run(onOpenReferences)}
							/>
							<PaletteItem
								icon={Globe2}
								label="Открыть браузер"
								shortcut="⌘T"
								keywords="источники интернет"
								onSelect={() => run(onOpenBrowser)}
							/>
							<PaletteItem
								icon={ShieldCheck}
								label="Открыть проверку"
								shortcut="⌃⇧G"
								keywords="ревью аудит основания"
								onSelect={() => run(onOpenReview)}
							/>
							<PaletteItem
								icon={SquareTerminal}
								label="Открыть терминал"
								shortcut="⌃`"
								keywords="команды консоль"
								onSelect={() => run(onOpenTerminal)}
							/>
							<PaletteItem
								icon={PanelLeft}
								label={
									navigationOpen
										? "Скрыть боковую панель"
										: "Показать боковую панель"
								}
								shortcut="⌘B"
								keywords="навигация сайдбар"
								onSelect={() => run(onToggleNavigation)}
							/>
							<PaletteItem
								icon={PanelRight}
								label={
									contextPanelOpen
										? "Скрыть контекстную панель"
										: "Показать контекстную панель"
								}
								keywords="инструменты правая панель"
								onSelect={() => run(onToggleContextPanel)}
							/>
							<PaletteItem
								icon={Settings}
								label="Открыть настройки"
								keywords="профиль аккаунт модели"
								onSelect={() => run(onOpenProfile)}
							/>
						</PaletteGroup>

						{threads.length > 0 ? (
							<PaletteGroup heading="Диалоги">
								{threads.map((thread) => (
									<PaletteItem
										key={thread.id}
										icon={SquarePen}
										label={thread.title?.trim() || "Новая задача"}
										keywords={`диалог чат ${thread.id}`}
										onSelect={() => run(() => onSelectThread(thread.id))}
									/>
								))}
							</PaletteGroup>
						) : null}

						{projects.length > 0 ? (
							<PaletteGroup heading="Проекты">
								{projects.map((project) => (
									<PaletteItem
										key={project.id}
										icon={FolderKanban}
										label={project.name}
										description={project.updatedAt ?? undefined}
										keywords={`проект объект ${project.id}`}
										onSelect={() => run(() => onSelectProject(project))}
									/>
								))}
							</PaletteGroup>
						) : null}

						{files.length > 0 ? (
							<PaletteGroup heading="Документы">
								{files.map((file) => (
									<PaletteItem
										key={file.id}
										icon={FileText}
										label={file.name}
										description={
											file.projectName
												? `${file.projectName} · ${file.status}`
												: file.status
										}
										keywords={`документ файл ${file.kind} ${file.projectName ?? ""}`}
										onSelect={() => run(() => onSelectFile(file))}
									/>
								))}
							</PaletteGroup>
						) : null}
					</Command.List>
				</Command>
			</DialogContent>
		</Dialog>
	);
}

function PaletteGroup({
	children,
	heading,
}: {
	children: ReactNode;
	heading: string;
}) {
	return (
		<Command.Group
			heading={heading}
			className="[&_[cmdk-group-heading]]:text-muted-foreground [&_[cmdk-group-heading]]:px-2.5 [&_[cmdk-group-heading]]:pt-2.5 [&_[cmdk-group-heading]]:pb-1 [&_[cmdk-group-heading]]:text-[11px] [&_[cmdk-group-heading]]:font-medium"
		>
			{children}
		</Command.Group>
	);
}

function PaletteItem({
	className,
	description,
	icon: Icon,
	keywords,
	label,
	onSelect,
	shortcut,
}: {
	className?: string;
	description?: string;
	icon: LucideIcon;
	keywords?: string;
	label: string;
	onSelect: () => void;
	shortcut?: string;
}) {
	return (
		<Command.Item
			value={`${label} ${keywords ?? ""}`}
			onSelect={onSelect}
			className={cn(
				"data-[selected=true]:bg-accent data-[selected=true]:text-accent-foreground flex min-h-10 cursor-default select-none items-center gap-3 rounded-lg px-2.5 py-2 text-sm outline-none",
				className,
			)}
		>
			<Icon
				aria-hidden="true"
				className="text-muted-foreground size-4 shrink-0"
			/>
			<span className="min-w-0 flex-1">
				<span className="block truncate">{label}</span>
				{description ? (
					<span className="text-muted-foreground mt-0.5 block truncate text-[11px]">
						{description}
					</span>
				) : null}
			</span>
			{shortcut ? (
				<kbd className="bg-muted text-muted-foreground rounded-md px-1.5 py-1 font-sans text-[10px] leading-none">
					{shortcut}
				</kbd>
			) : null}
		</Command.Item>
	);
}
