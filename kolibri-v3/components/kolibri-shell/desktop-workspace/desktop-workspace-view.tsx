"use client";

import type { ReactNode } from "react";
import { Thread, ThreadComposer } from "@/components/assistant-ui/thread";
import { KolibriPetHost } from "@/components/kolibri-shell/kolibri-pet";
import type { ProfileSettingsSection } from "@/components/kolibri-shell/profile-settings-surface";
import {
	WorkspaceCommandPalette,
	type WorkspaceCommandThread,
} from "@/components/kolibri-shell/workspace-command-palette";
import { WorkspaceHeader } from "@/components/kolibri-shell/workspace-header";
import {
	WorkspaceSidebar,
	type WorkspaceSidebarProps,
} from "@/components/kolibri-shell/workspace-sidebar";
import type { WorkspaceFile } from "@/components/kolibri-workspace";
import { WorkspaceTaskShelf } from "@/components/kolibri-workspace/workspace-task-shelf";
import type { WorkspaceProject } from "@/lib/workspace-types";
import type { AuxiliaryCanvasController } from "./use-auxiliary-canvas";
import { DesktopWorkspaceLayout } from "./desktop-workspace-layout";

export function DesktopWorkspaceView({
	activeDestination,
	activeProject,
	auxiliary,
	auxiliaryCanvas,
	auxiliaryDockedOpen,
	auxiliaryRenderFullscreen,
	commandPaletteOpen,
	composerContextOverride,
	currentTitle,
	navigationDockedOpen,
	navigationOpen,
	navigationOverlayOpen,
	onNewTask,
	onOpenChat,
	onOpenDocuments,
	onOpenFile,
	onOpenProject,
	onOpenProjects,
	onOpenReferences,
	onOpenSettings,
	onPaletteOpenChange,
	onSelectThread,
	onToggleNavigation,
	primaryContent,
	primaryOpen,
	projects,
	threads,
	workspaceFiles,
}: {
	activeDestination: WorkspaceSidebarProps["activeDestination"];
	activeProject: WorkspaceProject | null;
	auxiliary: AuxiliaryCanvasController;
	auxiliaryCanvas: ReactNode;
	auxiliaryDockedOpen: boolean;
	auxiliaryRenderFullscreen: boolean;
	commandPaletteOpen: boolean;
	composerContextOverride?: string;
	currentTitle: string;
	navigationDockedOpen: boolean;
	navigationOpen: boolean;
	navigationOverlayOpen: boolean;
	onNewTask: () => void;
	onOpenChat: () => void;
	onOpenDocuments: () => void;
	onOpenFile: (file: WorkspaceFile) => void;
	onOpenProject: (project: WorkspaceProject) => void;
	onOpenProjects: () => void;
	onOpenReferences: () => void;
	onOpenSettings: (section: ProfileSettingsSection) => void;
	onPaletteOpenChange: (open: boolean) => void;
	onSelectThread: (threadId: string) => void;
	onToggleNavigation: () => void;
	primaryContent: ReactNode;
	primaryOpen: boolean;
	projects: readonly WorkspaceProject[];
	threads: readonly WorkspaceCommandThread[];
	workspaceFiles: readonly WorkspaceFile[];
}) {
	const navigation = (
		<WorkspaceSidebar
			activeDestination={activeDestination}
			isOverlay={navigationOverlayOpen}
			onOpenAiModels={() => onOpenSettings("ai-models")}
			onOpenChat={onOpenChat}
			onOpenDocuments={onOpenDocuments}
			onOpenProfileSettings={() => onOpenSettings("general")}
			onOpenProjects={onOpenProjects}
			onOpenReferenceCatalog={onOpenReferences}
			onRequestClose={onToggleNavigation}
		/>
	);

	const chrome = (
		<>
			<WorkspaceCommandPalette
				contextPanelOpen={auxiliary.rightOpen || auxiliary.fullscreen}
				files={workspaceFiles}
				navigationOpen={navigationOpen}
				onNewTask={onNewTask}
				onOpenBrowser={() => auxiliary.openTool("browser")}
				onOpenChange={onPaletteOpenChange}
				onOpenDocuments={onOpenDocuments}
				onOpenProfile={() => onOpenSettings("general")}
				onOpenProjects={onOpenProjects}
				onOpenReferences={onOpenReferences}
				onOpenReview={() => auxiliary.openTool("review")}
				onOpenTerminal={() => auxiliary.openTool("terminal")}
				onSelectFile={onOpenFile}
				onSelectProject={onOpenProject}
				onSelectThread={onSelectThread}
				onToggleContextPanel={auxiliary.toggle}
				onToggleNavigation={onToggleNavigation}
				open={commandPaletteOpen}
				projects={projects}
				threads={threads}
			/>
			<WorkspaceTaskShelf
				className="fixed right-3 bottom-3 z-40 w-auto max-w-[min(34rem,calc(100vw-1.5rem))] rounded-xl border bg-background p-1.5 shadow-lg"
				tabs={auxiliary.session.tabs}
				onRestoreTab={auxiliary.restoreTab}
			/>
			<KolibriPetHost
				suppressed={auxiliary.open || commandPaletteOpen || primaryOpen}
			/>
		</>
	);
	const activeCanvasLabel = auxiliary.activeFile?.name
		? auxiliary.activeFile.name
		: auxiliary.activeTab?.title;
	const rightWorkspaceOpen = auxiliaryDockedOpen || auxiliaryRenderFullscreen;
	const settingsOpen =
		auxiliary.activeTab?.content.kind === "settings";
	const composerContextLabel =
		composerContextOverride ??
		(primaryOpen
			? activeCanvasLabel || "Рабочая область"
			: rightWorkspaceOpen
				? `Диалог · ${activeCanvasLabel || "Документы"}`
				: "Диалог");

	return (
		<>
			<DesktopWorkspaceLayout
				auxiliary={auxiliaryCanvas}
				auxiliaryFullscreen={auxiliaryRenderFullscreen}
				auxiliaryOpen={auxiliaryDockedOpen}
				chat={
					<Thread
						composerPlacement="workspace"
						onOpenAccount={() => onOpenSettings("general")}
						onOpenContextPanel={primaryOpen ? undefined : auxiliary.toggle}
						workspaceOpen={rightWorkspaceOpen}
					/>
				}
				chrome={chrome}
				composer={
					settingsOpen ? null : (
						<div
							data-slot="workspace-context-composer"
							data-composer-surface={primaryOpen ? "canvas" : "chat"}
							className="border-border/80 bg-background shrink-0 border-t px-3 pt-2 pb-[calc(0.75rem+env(safe-area-inset-bottom))]"
						>
							<div className="mx-auto w-full max-w-3xl">
								<div className="text-muted-foreground mb-1.5 flex min-w-0 items-center gap-1.5 px-1 text-[10px] leading-4">
									<span className="shrink-0">Контекст:</span>
									<span className="text-foreground truncate font-medium">
										{composerContextLabel}
									</span>
								</div>
								<ThreadComposer
									onOpenAccount={() => onOpenSettings("general")}
									onOpenContextPanel={
										primaryOpen ? undefined : auxiliary.toggle
									}
									workspaceOpen={rightWorkspaceOpen}
								/>
							</div>
						</div>
					)
				}
				header={
					<WorkspaceHeader
						activeProjectId={activeProject?.id}
						contextPanelOpen={rightWorkspaceOpen}
						navigationOpen={navigationOpen}
						onOpenChat={onOpenChat}
						onOpenCommandPalette={() => onPaletteOpenChange(true)}
						onProjectSelect={onOpenProject}
						onToggleContextPanel={
							primaryOpen ? undefined : auxiliary.toggle
						}
						onToggleNavigation={onToggleNavigation}
						projectName={activeProject?.name}
						projects={projects}
						threadTitle={currentTitle}
					/>
				}
				navigation={navigation}
				navigationOpen={navigationDockedOpen}
				primary={primaryContent}
				primaryOpen={primaryOpen}
			/>
			{navigationOverlayOpen ? (
				<div
					data-slot="workspace-navigation-overlay"
					className="fixed inset-0 z-50"
					role="dialog"
					aria-modal="true"
					aria-label="Навигация рабочего пространства"
				>
					<button
						type="button"
						aria-label="Закрыть навигацию"
						className="absolute inset-0 h-full w-full cursor-default bg-foreground/30"
						onClick={onToggleNavigation}
					/>
					<div className="absolute inset-y-0 left-0 flex w-[min(88vw,20rem)] flex-col border-r border-border bg-background shadow-2xl">
						{navigation}
					</div>
				</div>
			) : null}
		</>
	);
}
