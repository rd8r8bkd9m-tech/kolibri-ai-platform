"use client";

import { useCallback, useEffect, useState } from "react";
import type { WorkspaceFile } from "@/components/kolibri-workspace";
import {
	activateCanvasTab,
	type CanvasTabContent,
	closeCanvasTab,
	createCanvasSession,
	getActiveCanvasTab,
	minimizeCanvasTab,
	openCanvasTab,
	restoreCanvasTab,
	setCanvasTabSelectedFile,
	updateCanvasTab,
} from "@/components/kolibri-workspace/canvas-session";
import {
	CONTEXT_PANEL_TABS,
	type ContextPanelMode,
} from "@/components/kolibri-workspace/context-panel";
import {
	isOpenEstimateDetail,
	KOLIBRI_OPEN_ESTIMATE_EVENT,
} from "@/lib/workspace-events";
import type { WorkspaceProject } from "@/lib/workspace-types";

type OpenAuxiliaryTabInput = {
	content: CanvasTabContent;
	id: string;
	projectId?: string | null;
	selectedFile?: WorkspaceFile | null;
	title: string;
};

function toolTitle(mode: ContextPanelMode) {
	return (
		CONTEXT_PANEL_TABS.find((definition) => definition.id === mode)?.label ??
		"Инструмент"
	);
}

export function useAuxiliaryCanvas({
	activeProject,
	onInteraction,
	workspaceFiles,
}: {
	activeProject: WorkspaceProject | null;
	onInteraction: () => void;
	workspaceFiles: readonly WorkspaceFile[];
}) {
	const [session, setSession] = useState(() => createCanvasSession());
	const [visible, setVisible] = useState(false);
	const activeTab = getActiveCanvasTab(session);
	const open = visible && activeTab !== null;
	const fullscreen = open && Boolean(activeTab?.maximized);
	const visibleTabs = session.tabs.filter((tab) => !tab.minimized);
	const activeTool: ContextPanelMode | null =
		activeTab?.content.kind === "files"
			? "files"
			: activeTab?.content.kind === "tool"
				? activeTab.content.mode
				: null;
	const activeFile = activeTab?.selectedFile ?? null;

	useEffect(() => {
		setSession((current) =>
			createCanvasSession(
				current.tabs.map((tab) => {
					if (!tab.selectedFile) return tab;
					const refreshed = tab.selectedFile.documentId
						? workspaceFiles.find(
								(file) => file.documentId === tab.selectedFile?.documentId,
							)
						: workspaceFiles.find((file) => file.id === tab.selectedFile?.id);
					return { ...tab, selectedFile: refreshed ?? tab.selectedFile };
				}),
				current.activeTabId,
			),
		);
	}, [workspaceFiles]);

	const openTab = useCallback(
		({
			content,
			id,
			projectId = activeProject?.id ?? null,
			selectedFile = null,
			title,
		}: OpenAuxiliaryTabInput) => {
			setSession((current) =>
				openCanvasTab(current, {
					content,
					id,
					placement: "right",
					projectId,
					selectedFile,
					title,
				}),
			);
			setVisible(true);
			onInteraction();
		},
		[activeProject?.id, onInteraction],
	);

	const openTool = useCallback(
		(mode: ContextPanelMode) => {
			openTab({
				content:
					mode === "files"
						? { kind: "files", category: "all" }
						: { kind: "tool", mode },
				id: `auxiliary:${activeProject?.id ?? "workspace"}:${mode}`,
				title: toolTitle(mode),
			});
		},
		[activeProject?.id, openTab],
	);

	const openProjects = useCallback(() => {
		openTab({
			content: { kind: "projects" },
			id: "auxiliary:projects",
			title: "Проекты",
		});
	}, [openTab]);

	const openReferences = useCallback(() => {
		openTab({
			content: { kind: "references" },
			id: "auxiliary:references",
			title: "Справочники",
		});
	}, [openTab]);

	const openFiles = useCallback(
		(input: {
			category?: WorkspaceFile["category"];
			projectId?: string | null;
			title?: string;
		} = {}) => {
			const projectId = input.projectId ?? activeProject?.id ?? null;
			openTab({
				content: { kind: "files", category: input.category ?? "all" },
				id: `auxiliary:files:${projectId ?? "workspace"}`,
				projectId,
				title:
					input.title ??
					(projectId ? `Документы · ${projectId}` : "Документы"),
			});
		},
		[activeProject?.id, openTab],
	);

	const openProject = useCallback(
		(project: WorkspaceProject) => {
			openTab({
				content: { kind: "files", category: "all" },
				id: `auxiliary:project:${project.id}`,
				projectId: project.id,
				title: project.name,
			});
		},
		[openTab],
	);

	const openFile = useCallback(
		(file: WorkspaceFile) => {
			openTab({
				content: { kind: "files", category: file.category },
				id: `artifact:${file.documentId ?? file.id}`,
				projectId: file.projectId ?? null,
				selectedFile: file,
				title: file.name,
			});
		},
		[openTab],
	);

	const toggle = useCallback(() => {
		if (open) {
			setVisible(false);
			return;
		}
		if (activeTab) {
			setVisible(true);
			return;
		}
		openTab({
			content: { kind: "launcher" },
			id: "auxiliary:launcher",
			title: "Инструменты",
		});
	}, [activeTab, open, openTab]);

	const updateTool = useCallback(
		(mode: ContextPanelMode | null) => {
			if (!activeTab) return;
			setSession((current) =>
				updateCanvasTab(current, activeTab.id, {
					content:
						mode === null
							? { kind: "launcher" }
							: mode === "files"
								? { kind: "files", category: "all" }
								: { kind: "tool", mode },
					selectedFile: null,
					title: mode === null ? "Инструменты" : toolTitle(mode),
				}),
			);
		},
		[activeTab],
	);

	const close = useCallback(() => {
		if (!activeTab) return;
		const next = closeCanvasTab(session, activeTab.id);
		setSession(next);
		setVisible(getActiveCanvasTab(next) !== null);
	}, [activeTab, session]);

	const minimize = useCallback(() => {
		if (!activeTab) return;
		const next = minimizeCanvasTab(session, activeTab.id);
		setSession(next);
		setVisible(getActiveCanvasTab(next) !== null);
	}, [activeTab, session]);

	const selectTab = useCallback((tabId: string) => {
		setSession((current) => activateCanvasTab(current, tabId));
		setVisible(true);
	}, []);

	const toggleFullscreen = useCallback(() => {
		if (!activeTab) return;
		setSession((current) =>
			updateCanvasTab(current, activeTab.id, {
				maximized: !activeTab.maximized,
			}),
		);
	}, [activeTab]);

	const selectFile = useCallback(
		(file: WorkspaceFile | null) => {
			if (!activeTab) return;
			setSession((current) =>
				setCanvasTabSelectedFile(current, activeTab.id, file),
			);
		},
		[activeTab],
	);

	const restoreTab = useCallback((tabId: string) => {
		setSession((current) => restoreCanvasTab(current, tabId));
		setVisible(true);
	}, []);

	useEffect(() => {
		const openEstimate = (event: Event) => {
			const detail = event instanceof CustomEvent ? event.detail : null;
			if (!isOpenEstimateDetail(detail)) return;
			const known = workspaceFiles.find(
				(file) => file.documentId === detail.documentId,
			);
			const file: WorkspaceFile = known
				? {
						...known,
						name: detail.title,
						projectId: detail.projectId,
						projectName: detail.projectName || known.projectName,
						version: Math.max(known.version ?? 0, detail.version),
					}
				: {
						category: "estimates",
						documentId: detail.documentId,
						editable: true,
						id: detail.documentId,
						kind: "estimate",
						modifiedAt: "сейчас",
						name: detail.title,
						projectId: detail.projectId,
						projectName: detail.projectName,
						size: "Смета",
						status: "Черновик",
						version: detail.version,
					};
			openTab({
				content: { kind: "files", category: "estimates" },
				id: `artifact:${detail.documentId}`,
				projectId: detail.projectId,
				selectedFile: file,
				title: detail.title,
			});
		};
		window.addEventListener(KOLIBRI_OPEN_ESTIMATE_EVENT, openEstimate);
		return () =>
			window.removeEventListener(KOLIBRI_OPEN_ESTIMATE_EVENT, openEstimate);
	}, [openTab, workspaceFiles]);

	return {
		activeFile,
		activeTab,
		activeTool,
		close,
		fullscreen,
		minimize,
		open,
		openFile,
		openFiles,
		openProject,
		openProjects,
		openReferences,
		openTool,
		restoreTab,
		selectFile,
		selectTab,
		session,
		toggle,
		toggleFullscreen,
		updateTool,
		visibleTabs,
	};
}

export type AuxiliaryCanvasController = ReturnType<typeof useAuxiliaryCanvas>;
