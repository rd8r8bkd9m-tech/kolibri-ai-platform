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
import { WorkspaceProjectPicker } from "@/components/kolibri-shell/workspace-project-picker";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
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

const WORKSPACE_TOOL_SHORTCUTS: Record<ContextPanelMode, string> = {
	review: "⌃⇧G",
	terminal: "⌃`",
	browser: "⌘T",
	files: "⌘P",
};

const WORKSPACE_TOOLS = CONTEXT_PANEL_TABS.map((tool) => ({
	...tool,
	shortcut: WORKSPACE_TOOL_SHORTCUTS[tool.id],
}));

const CANVAS_HEADER_TABS: readonly CanvasFrameHeaderTab[] =
	WORKSPACE_TOOLS.map(({ icon, id, label }) => ({
		icon,
		id,
		title: label,
	}));

function isContextPanelMode(value: string): value is ContextPanelMode {
	return CONTEXT_PANEL_TABS.some((tab) => tab.id === value);
}

function WorkspaceLauncher({
	onSelect,
}: {
	onSelect: (mode: ContextPanelMode) => void;
}) {
	return (
		<nav
			aria-label="Инструменты рабочей области"
			className="flex min-h-0 flex-1 items-center justify-center px-5 py-10"
		>
			<ul className="w-full max-w-[20rem] space-y-1">
				{WORKSPACE_TOOLS.map(({ id, icon: Icon, label, shortcut }) => (
					<li key={id}>
						<Tooltip>
							<TooltipTrigger asChild>
								<button
									type="button"
									onClick={() => onSelect(id)}
									className="hover:bg-muted/55 focus-visible:ring-ring flex h-12 w-full items-center gap-3 rounded-lg px-3 text-left text-[13px] font-medium transition-colors outline-none focus-visible:ring-2"
								>
									<Icon
										className="text-muted-foreground size-4 shrink-0"
										aria-hidden="true"
									/>
									<span>{label}</span>
									{shortcut ? (
										<kbd className="bg-muted text-muted-foreground ml-auto rounded-full px-1.5 py-0.5 text-[10px] leading-none font-medium">
											{shortcut}
										</kbd>
									) : null}
								</button>
							</TooltipTrigger>
							<TooltipContent side="left" sideOffset={10}>
								Открыть: {label.toLocaleLowerCase("ru-RU")}
							</TooltipContent>
						</Tooltip>
					</li>
				))}
			</ul>
		</nav>
	);
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
				: (resolvedMode ?? "launcher");

	return (
		<CanvasFrame
			activeTabId={activeSessionTabId}
			activeHeaderTabId={surfaceContent ? undefined : activeTool ?? undefined}
			compactChrome={compactChrome}
			headerActions={
				<WorkspaceProjectPicker
					activeProjectId={activeProjectId}
					onProjectSelect={onProjectSelect}
					projectName={trimmedProjectName}
					projects={projects}
				/>
			}
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
						onBack={
							compactChrome
								? undefined
								: (onFilesBack ?? (() => setActiveTool(null)))
						}
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
					<WorkspaceLauncher
						onSelect={(nextTool) => {
							setOpenFile(null);
							setActiveTool(nextTool);
						}}
					/>
				)}
			</div>
		</CanvasFrame>
	);
}
