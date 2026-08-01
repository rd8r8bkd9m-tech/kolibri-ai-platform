"use client";

import { CanvasWorkspace, type WorkspaceFile } from "@/components/kolibri-workspace";
import type { WorkspaceCatalogLoadState } from "@/lib/workspace-documents";
import type { WorkspaceProject } from "@/lib/workspace-types";
import { cn } from "@/lib/utils";
import type { AuxiliaryCanvasController } from "./use-auxiliary-canvas";

export function DesktopAuxiliaryCanvas({
	catalogState,
	controller,
	onOpenSettings,
	onRefresh,
	projects,
	workspaceFiles,
}: {
	catalogState: WorkspaceCatalogLoadState;
	controller: AuxiliaryCanvasController;
	onOpenSettings: () => void;
	onRefresh: () => void;
	projects: readonly WorkspaceProject[];
	workspaceFiles: readonly WorkspaceFile[];
}) {
	const { activeFile, activeTab, activeTool } = controller;
	if (!activeTab) return null;

	const project = activeTab.projectId
		? projects.find((candidate) => candidate.id === activeTab.projectId)
		: null;
	const files = activeTab.projectId
		? workspaceFiles.filter((file) => file.projectId === activeTab.projectId)
		: workspaceFiles;

	return (
		<div
			id="workspace-canvas"
			data-slot="auxiliary-canvas"
			className={cn(
				"h-full min-h-0 min-w-0 overflow-hidden bg-background",
				controller.fullscreen && "fixed inset-0 z-50 h-dvh w-dvw",
			)}
		>
			<CanvasWorkspace
				activeSessionTabId={activeTab.id}
				fileCategory={
					activeTab.content.kind === "files"
						? activeTab.content.category
						: "all"
				}
				maximized={activeTab.maximized}
				placement="right"
				projectName={project?.name}
				selectedFile={activeFile}
				sessionTabs={controller.visibleTabs}
				surfaceMode={activeTab.content.kind}
				toolMode={activeTool}
				workspaceCatalogState={catalogState}
				workspaceFiles={files}
				onClose={controller.close}
				onFilesBack={() => controller.updateTool(null)}
				onMinimize={controller.minimize}
				onOpenSettings={onOpenSettings}
				onRetryWorkspaceCatalog={onRefresh}
				onSelectedFileChange={controller.selectFile}
				onSessionTabSelect={controller.selectTab}
				onToggleMaximize={controller.toggleFullscreen}
				onToolModeChange={controller.updateTool}
			/>
		</div>
	);
}
