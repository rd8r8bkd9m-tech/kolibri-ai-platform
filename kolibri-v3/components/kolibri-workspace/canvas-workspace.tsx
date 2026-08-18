"use client";

import { type ReactNode, useEffect, useState } from "react";
import {
	CanvasFrame,
	type CanvasFrameHeaderTab,
} from "@/components/kolibri-workspace/canvas-frame";
import {
	CONTEXT_PANEL_TABS,
	ContextPanel,
	type ContextPanelMode,
} from "@/components/kolibri-workspace/context-panel";
import { WorkspaceArtifactEditor } from "@/components/kolibri-workspace/workspace-artifact-editor";
import {
	type WorkspaceFile,
	type WorkspaceFileCategory,
	WorkspaceFileManager,
} from "@/components/kolibri-workspace/workspace-file-manager";
import type { WorkspaceCatalogLoadState } from "@/lib/workspace-documents";
import type { WorkspaceProject } from "@/lib/workspace-types";
import {
	CANVAS_VIEW_REGISTRY,
	isCanvasMode,
	type CanvasMode,
} from "./canvas-view-registry";

export { CANVAS_VIEW_ALLOWLIST } from "./canvas-view-registry";
export type { CanvasMode } from "./canvas-view-registry";
export type CanvasPlacement = "bottom" | "primary" | "right";

export type CanvasSessionTabPresentation = {
	id: string;
	title: string;
};

export interface CanvasWorkspaceProps {
	activeSessionTabId?: string;
	activeProjectId?: string | null;
	compactChrome?: boolean;
	fileCategory?: WorkspaceFileCategory;
	maximized?: boolean;
	projectName?: string;
	mode?: CanvasMode;
	onClose?: () => void;
	onCreateInChat?: () => void;
	onFilesBack?: () => void;
	onMinimize?: () => void;
	onOpenSettings?: () => void;
	onProjectSelect?: (project: WorkspaceProject) => void;
	onRetryWorkspaceCatalog?: () => void;
	onSelectedFileChange?: (file: WorkspaceFile | null) => void;
	onPlacementChange?: (placement: CanvasPlacement) => void;
	onSessionTabSelect?: (tabId: string) => void;
	onToolModeChange?: (mode: ContextPanelMode | null) => void;
	onToggleMaximize?: () => void;
	placement?: CanvasPlacement;
	projects?: readonly WorkspaceProject[];
	selectedFile?: WorkspaceFile | null;
	sessionTabs?: readonly CanvasSessionTabPresentation[];
	surfaceContent?: ReactNode;
	surfaceMode?: string;
	toolMode?: ContextPanelMode | null;
	workspaceFiles?: readonly WorkspaceFile[];
	workspaceCatalogState?: WorkspaceCatalogLoadState;
}

const CANVAS_HEADER_TABS: readonly CanvasFrameHeaderTab[] =
	CONTEXT_PANEL_TABS.map(({ icon, id, label }) => ({
		icon,
		id,
		title: label,
	}));

function isContextPanelMode(value: string): value is ContextPanelMode {
	return CONTEXT_PANEL_TABS.some((tab) => tab.id === value);
}

export function CanvasWorkspace({
	activeSessionTabId,
	activeProjectId,
	compactChrome = false,
	fileCategory = "all",
	maximized = false,
	projectName,
	mode,
	onClose,
	onCreateInChat,
	onFilesBack,
	onMinimize,
	onOpenSettings,
	onProjectSelect,
	onRetryWorkspaceCatalog,
	onSelectedFileChange,
	onPlacementChange,
	onSessionTabSelect,
	onToolModeChange,
	onToggleMaximize,
	placement = "right",
	projects = [],
	selectedFile,
	sessionTabs = [],
	surfaceContent,
	surfaceMode,
	toolMode,
	workspaceFiles = [],
	workspaceCatalogState = "ready",
}: CanvasWorkspaceProps) {
	const [internalTool, setInternalTool] = useState<ContextPanelMode | null>(
		toolMode ?? null,
	);
	const [internalSelectedFile, setInternalSelectedFile] =
		useState<WorkspaceFile | null>(selectedFile ?? null);
	const activeTool = toolMode === undefined ? internalTool : toolMode;
	const openFile =
		selectedFile === undefined ? internalSelectedFile : selectedFile;
	const setOpenFile = (file: WorkspaceFile | null) => {
		setInternalSelectedFile(file);
		onSelectedFileChange?.(file);
	};
	const setActiveTool = (nextTool: ContextPanelMode | null) => {
		setInternalTool(nextTool);
		onToolModeChange?.(nextTool);
	};
	const resolvedMode = isCanvasMode(mode) ? mode : null;
	const definition = resolvedMode
		? CANVAS_VIEW_REGISTRY.get(resolvedMode)?.payload
		: null;
	const CanvasView = definition?.component;
	const trimmedProjectName = projectName?.trim();
	const projectLabel = trimmedProjectName || "Проект не выбран";

	useEffect(() => {
		if (toolMode !== undefined) {
			setInternalTool(toolMode);
			if (toolMode !== "files") {
				setOpenFile(null);
			}
		}
	}, [toolMode]);

	const canvasMode = surfaceContent
		? (surfaceMode ?? "surface")
		: openFile
			? `artifact-${openFile.kind}`
			: activeTool
				? `tool-${activeTool}`
				: (resolvedMode ?? "files");

	return (
		<CanvasFrame
			activeTabId={activeSessionTabId}
			activeHeaderTabId={surfaceContent ? undefined : activeTool ?? "files"}
			compactChrome={compactChrome}
			headerActions={null}
			headerTabs={CANVAS_HEADER_TABS}
			label="Рабочая область проекта"
			maximized={maximized}
			onClose={onClose}
			onHeaderTabSelect={(nextTool) => {
				if (!isContextPanelMode(nextTool)) return;
				setOpenFile(null);
				setActiveTool(nextTool);
			}}
			onMinimize={onMinimize}
			onPlacementChange={onPlacementChange}
			onTabSelect={onSessionTabSelect}
			onToggleMaximize={onToggleMaximize}
			placement={placement}
			tabs={sessionTabs}
		>
			<div
				data-testid="canvas-workspace"
				data-canvas-mode={canvasMode}
				className="flex min-h-0 flex-1 flex-col"
			>
				{surfaceContent ? (
					surfaceContent
				) : openFile ? (
					<WorkspaceArtifactEditor
						key={openFile.id}
						compactChrome={compactChrome}
						file={openFile}
						projectLabel={projectLabel}
						onBack={() => setOpenFile(null)}
					/>
				) : activeTool === "files" ? (
					<WorkspaceFileManager
						catalogState={workspaceCatalogState}
						files={workspaceFiles}
						initialCategory={fileCategory}
						projectLabel={projectLabel}
						onBack={compactChrome ? undefined : onFilesBack}
						onCreateInChat={onCreateInChat}
						onOpenFile={setOpenFile}
						onRetry={onRetryWorkspaceCatalog}
					/>
				) : activeTool ? (
					<ContextPanel
						embedded
						projectName={projectLabel}
						mode={activeTool}
						onClose={() => setActiveTool(null)}
						onOpenSettings={onOpenSettings}
					/>
				) : CanvasView && definition ? (
					<CanvasView projectLabel={projectLabel} />
				) : (
					<WorkspaceFileManager
						catalogState={workspaceCatalogState}
						files={workspaceFiles}
						initialCategory={fileCategory}
						projectLabel={projectLabel}
						onCreateInChat={onCreateInChat}
						onOpenFile={setOpenFile}
						onRetry={onRetryWorkspaceCatalog}
					/>
				)}
			</div>
		</CanvasFrame>
	);
}
