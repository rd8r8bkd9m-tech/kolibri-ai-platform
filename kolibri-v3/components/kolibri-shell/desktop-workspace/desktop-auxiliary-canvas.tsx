"use client";

import {
	CanvasWorkspace,
	ProjectsOverview,
	ReferenceCatalog,
	type WorkspaceFile,
} from "@/components/kolibri-workspace";
import { WorkspaceArtifactEditor } from "@/components/kolibri-workspace/workspace-artifact-editor";
import { WorkspaceFileManager } from "@/components/kolibri-workspace/workspace-file-manager";
import {
	ProfileSettingsSurface,
	type ProfileSettingsSection,
} from "@/components/kolibri-shell/profile-settings-surface";
import type { WorkspaceCatalogLoadState } from "@/lib/workspace-documents";
import type { WorkspaceProject } from "@/lib/workspace-types";
import { cn } from "@/lib/utils";
import type { AuxiliaryCanvasController } from "./use-auxiliary-canvas";

export function DesktopAuxiliaryCanvas({
	catalogState,
	controller,
	onSelectProject,
	onRefresh,
	projects,
	workspaceFiles,
}: {
	catalogState: WorkspaceCatalogLoadState;
	controller: AuxiliaryCanvasController;
	onSelectProject: (project: WorkspaceProject) => void;
	onRefresh: () => void;
	projects: readonly WorkspaceProject[];
	workspaceFiles: readonly WorkspaceFile[];
}) {
	const { activeFile, activeTab, activeTool } = controller;
	if (!activeTab) return null;

	if (activeTab.content.kind === "settings") {
		const settingsSection = activeTab.content.section as ProfileSettingsSection;
		return (
			<div
				id="workspace-canvas"
				data-slot="auxiliary-canvas"
				data-canvas-kind="settings"
				className="@container h-full min-h-0 min-w-0 overflow-hidden bg-background"
			>
				<ProfileSettingsSurface
					activeSection={settingsSection}
					onSectionChange={controller.openSettings}
				/>
			</div>
		);
	}

	const project = activeTab.projectId
		? projects.find((candidate) => candidate.id === activeTab.projectId)
		: null;
	const files = activeTab.projectId
		? workspaceFiles.filter((file) => file.projectId === activeTab.projectId)
		: workspaceFiles;
	const projectLabel = project?.name ?? "Проект не выбран";

	if (activeTab.content.kind === "projects") {
		return (
			<div
				id="workspace-canvas"
				data-slot="auxiliary-canvas"
				data-canvas-kind="projects"
				className="@container h-full min-h-0 min-w-0 overflow-hidden bg-background"
			>
				<ProjectsOverview
					activeProjectId={activeTab.projectId}
					catalogState={catalogState}
					onOpenProject={onSelectProject}
					onRetry={onRefresh}
					projects={projects}
				/>
			</div>
		);
	}

	if (activeTab.content.kind === "references") {
		return (
			<div
				id="workspace-canvas"
				data-slot="auxiliary-canvas"
				data-canvas-kind="references"
				className="@container h-full min-h-0 min-w-0 overflow-hidden bg-background"
			>
				<ReferenceCatalog projectId={activeTab.projectId} />
			</div>
		);
	}

	if (
		activeTab.content.kind === "files" &&
		activeTab.placement === "primary"
	) {
		return (
			<div
				id="workspace-canvas"
				data-slot="auxiliary-canvas"
				data-canvas-kind={activeFile ? "artifact" : "documents"}
				className="@container flex h-full min-h-0 min-w-0 flex-col overflow-hidden bg-background"
			>
				{activeFile ? (
					<WorkspaceArtifactEditor
						file={activeFile}
						onBack={() => controller.selectFile(null)}
						projectLabel={activeFile.projectName || projectLabel}
					/>
				) : (
					<WorkspaceFileManager
						catalogState={catalogState}
						files={files}
						initialCategory={activeTab.content.category}
						onOpenFile={controller.selectFile}
						onRetry={onRefresh}
						projectLabel={projectLabel}
						title="Документы"
					/>
				)}
			</div>
		);
	}

	return (
		<div
			id="workspace-canvas"
			data-slot="auxiliary-canvas"
			data-canvas-placement={activeTab.placement}
			className={cn(
				"h-full min-h-0 min-w-0 overflow-hidden bg-background",
				controller.fullscreen && "fixed inset-0 z-50 h-dvh w-dvw",
			)}
		>
			<CanvasWorkspace
				activeSessionTabId={activeTab.id}
				activeProjectId={project?.id ?? activeTab.projectId}
				fileCategory={
					activeTab.content.kind === "files"
						? activeTab.content.category
						: "all"
				}
				maximized={activeTab.maximized}
				placement={activeTab.placement}
				projectName={project?.name}
				projects={projects}
				selectedFile={activeFile}
				sessionTabs={controller.visibleTabs}
				surfaceMode={activeTab.content.kind}
				toolMode={activeTool}
				workspaceCatalogState={catalogState}
				workspaceFiles={files}
				onClose={controller.close}
				onFilesBack={() => controller.updateTool(null)}
				onMinimize={controller.minimize}
				onOpenSettings={() => controller.openSettings("integrations")}
				onProjectSelect={onSelectProject}
				onRetryWorkspaceCatalog={onRefresh}
				onSelectedFileChange={controller.selectFile}
				onSessionTabSelect={controller.selectTab}
				onToggleMaximize={controller.toggleFullscreen}
				onToolModeChange={controller.updateTool}
			/>
		</div>
	);
}
