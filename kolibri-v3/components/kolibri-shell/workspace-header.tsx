"use client";

import { ThreadListPrimitive } from "@assistant-ui/react";
import {
	ArrowLeft,
	Folder,
	PanelLeft,
	PanelRight,
	Search,
	SquarePen,
} from "lucide-react";
import { ChromeActionButton } from "@/components/kolibri-shell/chrome-action-button";
import {
	SHELL_DESKTOP_HEADER_ICON_WRAPPER,
	SHELL_HEADER_ICON_BUTTON_CLASS,
	SHELL_ICON_SIZE_CLASS,
	SHELL_ICON_STROKE_WIDTH,
} from "@/components/kolibri-shell/header-design-system";
import { Button } from "@/components/ui/button";
import {
	Tooltip,
	TooltipContent,
	TooltipProvider,
	TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import type { WorkspaceProject } from "@/lib/workspace-types";
import { uiClassTokens } from "@/components/ui/class-names";
import { WorkspaceProjectPicker } from "./workspace-project-picker";

export type WorkspaceHeaderProps = {
	activeProjectId?: string | null;
	contextPanelOpen: boolean;
	className?: string;
	navigationOpen: boolean;
	onBack?: () => void;
	onNavigationPreviewEnter?: () => void;
	onNavigationPreviewLeave?: () => void;
	onOpenChat?: () => void;
	onOpenCommandPalette: () => void;
	onToggleContextPanel?: () => void;
	onProjectSelect?: (project: WorkspaceProject) => void;
	onToggleNavigation: () => void;
	projectName?: string;
	projects?: readonly WorkspaceProject[];
	threadTitle?: string;
};

export function WorkspaceHeader({
	activeProjectId,
	contextPanelOpen,
	className,
	navigationOpen,
	onBack,
	onNavigationPreviewEnter,
	onNavigationPreviewLeave,
	onOpenChat,
	onOpenCommandPalette,
	onToggleContextPanel,
	onProjectSelect,
	onToggleNavigation,
	projectName,
	projects = [],
	threadTitle = "Новая задача",
}: WorkspaceHeaderProps) {
	const projectLabel = projectName?.trim() || null;

	return (
		<TooltipProvider delayDuration={350}>
			<header
				className={cn(
					uiClassTokens.workspaceHeaderRoot,
					className,
				)}
			>
				{!navigationOpen ? (
					<>
						<ChromeActionButton
							label="Переключить боковую панель"
							shortcut="⌘B"
							iconOnly
							size="icon-xs"
							aria-controls="workspace-project-navigation"
							aria-expanded={false}
							onClick={onToggleNavigation}
							onMouseEnter={onNavigationPreviewEnter}
							onMouseLeave={onNavigationPreviewLeave}
							className={cn(SHELL_HEADER_ICON_BUTTON_CLASS, "relative")}
							iconWrapperClassName={cn(
								SHELL_DESKTOP_HEADER_ICON_WRAPPER,
								"items-center justify-center",
							)}
						>
							<PanelLeft
								className={SHELL_ICON_SIZE_CLASS}
								aria-hidden="true"
								strokeWidth={SHELL_ICON_STROKE_WIDTH}
							/>
							<span
								aria-hidden="true"
								className="absolute top-0.5 right-0.5 size-1.5 rounded-full bg-[#339cff]"
							/>
						</ChromeActionButton>
						<HeaderNewThreadButton onOpenChat={onOpenChat} />
						<span
							aria-hidden="true"
							className={uiClassTokens.workspaceHeaderDivider}
						/>
					</>
				) : null}

				{onBack ? (
					<ChromeActionButton
						label="Назад к диалогу"
						iconOnly
						size="icon-xs"
						data-slot="workspace-header-back"
						className={SHELL_HEADER_ICON_BUTTON_CLASS}
						iconWrapperClassName={SHELL_DESKTOP_HEADER_ICON_WRAPPER}
						onClick={onBack}
					>
						<ArrowLeft
							className={SHELL_ICON_SIZE_CLASS}
							aria-hidden="true"
							strokeWidth={SHELL_ICON_STROKE_WIDTH}
						/>
					</ChromeActionButton>
				) : null}

				<Folder
					className={`text-muted-foreground ml-0.5 ${SHELL_ICON_SIZE_CLASS} shrink-0`}
					aria-hidden="true"
					strokeWidth={SHELL_ICON_STROKE_WIDTH}
				/>
				<p className={uiClassTokens.workspaceHeaderThreadTitle}>
					{threadTitle}
				</p>

				<div className="ml-auto flex shrink-0 items-center gap-1">
					<ChromeActionButton
						label="Команды и поиск"
						shortcut="⌘K"
						iconOnly
						size="icon-xs"
						data-command-palette-launcher="header"
						className={SHELL_HEADER_ICON_BUTTON_CLASS}
						iconWrapperClassName={SHELL_DESKTOP_HEADER_ICON_WRAPPER}
						onClick={onOpenCommandPalette}
					>
						<Search
							className={`${SHELL_ICON_SIZE_CLASS} shrink-0`}
							aria-hidden="true"
							strokeWidth={SHELL_ICON_STROKE_WIDTH}
						/>
					</ChromeActionButton>
					<WorkspaceProjectPicker
						activeProjectId={activeProjectId}
						onProjectSelect={onProjectSelect}
						projectName={projectLabel ?? undefined}
						projects={projects}
					/>

					{onToggleContextPanel ? (
						<ChromeActionButton
							label={
								contextPanelOpen ? "Скрыть контекст" : "Показать контекст"
							}
							iconOnly
							size="icon-xs"
							data-context-launcher="header"
							aria-controls="workspace-canvas"
							aria-expanded={contextPanelOpen}
							aria-pressed={contextPanelOpen}
							className={cn(
								SHELL_HEADER_ICON_BUTTON_CLASS,
								contextPanelOpen && "bg-muted text-foreground",
							)}
							iconWrapperClassName={cn(
								SHELL_DESKTOP_HEADER_ICON_WRAPPER,
								"items-center justify-center",
							)}
							onClick={onToggleContextPanel}
						>
							<PanelRight
								className={`${SHELL_ICON_SIZE_CLASS} shrink-0`}
								aria-hidden="true"
								strokeWidth={SHELL_ICON_STROKE_WIDTH}
							/>
						</ChromeActionButton>
					) : null}
				</div>
			</header>
		</TooltipProvider>
	);
}

function HeaderNewThreadButton({ onOpenChat }: { onOpenChat?: () => void }) {
	return (
		<Tooltip>
			<TooltipTrigger asChild>
				<ThreadListPrimitive.New asChild>
					<Button
						type="button"
						variant="ghost"
						size="icon-xs"
						onClick={onOpenChat}
						className={SHELL_HEADER_ICON_BUTTON_CLASS}
						aria-label="Новая задача"
					>
						<SquarePen
							className={`${SHELL_ICON_SIZE_CLASS} shrink-0`}
							aria-hidden="true"
							strokeWidth={SHELL_ICON_STROKE_WIDTH}
						/>
					</Button>
				</ThreadListPrimitive.New>
			</TooltipTrigger>
			<TooltipContent side="bottom" sideOffset={8}>
				Новая задача
			</TooltipContent>
		</Tooltip>
	);
}
