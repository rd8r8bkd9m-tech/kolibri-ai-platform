"use client";

import {
	useAssistantContext,
	useAssistantInstructions,
	useAui,
	useAuiState,
} from "@assistant-ui/react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ProfileSettingsSection } from "@/components/kolibri-shell/profile-settings-surface";
import type { WorkspaceFile } from "@/components/kolibri-workspace";
import {
	isActivateAgentTaskDetail,
	KOLIBRI_ACTIVATE_AGENT_TASK_EVENT,
	KOLIBRI_OPEN_MODEL_SETTINGS_EVENT,
} from "@/lib/workspace-events";
import type { WorkspaceProject } from "@/lib/workspace-types";
import {
	WORKSPACE_CONTEXT_SCHEMA_VERSION,
	type WorkspaceContextTab,
	type WorkspaceContextV1,
	type WorkspaceSurface,
} from "@/lib/workspace-context";
import { usePublishWorkspaceContext } from "@/lib/workspace-context-provider";
import { DesktopAuxiliaryCanvas } from "./desktop-auxiliary-canvas";
import { DesktopWorkspaceView } from "./desktop-workspace-view";
import { useAuxiliaryCanvas } from "./use-auxiliary-canvas";
import { useDesktopWorkspaceShortcuts } from "./use-desktop-workspace-shortcuts";
import { useWorkspaceDocumentCatalog } from "./use-workspace-document-catalog";

export function DesktopWorkspace() {
	const aui = useAui();
	const {
		files: workspaceFiles,
		refresh,
		state: catalogState,
	} = useWorkspaceDocumentCatalog();
	const threadItems = useAuiState((state) => state.threads.threadItems);
	const activeThreadId = useAuiState((state) => state.threads.mainThreadId);
	const activeThread = threadItems.find(
		(thread) => thread.id === activeThreadId,
	);
	const [navigationOpen, setNavigationOpen] = useState(true);
	const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);
	const [activeComposerTask, setActiveComposerTask] = useState<{
		runId: string;
		threadId: string;
	} | null>(null);
	const [activeProject, setActiveProject] = useState<WorkspaceProject | null>(
		null,
	);

	const projects = useMemo(() => {
		const byId = new Map<string, WorkspaceProject>();
		for (const file of workspaceFiles) {
			if (!file.projectId || !file.projectName) continue;
			byId.set(file.projectId, {
				id: file.projectId,
				name: file.projectName,
				updatedAt: file.modifiedAt,
			});
		}
		return [...byId.values()];
	}, [workspaceFiles]);

	const handleCanvasInteraction = useCallback(() => undefined, []);
	const auxiliary = useAuxiliaryCanvas({
		activeProject,
		onInteraction: handleCanvasInteraction,
		workspaceFiles,
	});
	const settingsCanvasOpen =
		auxiliary.open && auxiliary.activeTab?.content.kind === "settings";
	const navigationBeforeSettingsRef = useRef<boolean | null>(null);
	const navigationChangedDuringSettingsRef = useRef(false);
	const settingsCanvasWasOpenRef = useRef(false);

	useEffect(() => {
		const wasOpen = settingsCanvasWasOpenRef.current;
		if (settingsCanvasOpen && !wasOpen) {
			navigationBeforeSettingsRef.current = navigationOpen;
			navigationChangedDuringSettingsRef.current = false;
			if (navigationOpen) setNavigationOpen(false);
		} else if (!settingsCanvasOpen && wasOpen) {
			const previousNavigationState = navigationBeforeSettingsRef.current;
			navigationBeforeSettingsRef.current = null;
			if (
				previousNavigationState !== null &&
				!navigationChangedDuringSettingsRef.current
			) {
				setNavigationOpen(previousNavigationState);
			}
			navigationChangedDuringSettingsRef.current = false;
		}
		settingsCanvasWasOpenRef.current = settingsCanvasOpen;
	}, [navigationOpen, settingsCanvasOpen]);

	const toggleNavigation = useCallback(() => {
		if (settingsCanvasOpen) {
			navigationChangedDuringSettingsRef.current = true;
		}
		setNavigationOpen((open) => !open);
	}, [settingsCanvasOpen]);

	const workspaceContext = useMemo<WorkspaceContextV1>(() => {
		const toContextTab = (
			tab: NonNullable<typeof auxiliary.activeTab>,
		): WorkspaceContextTab => ({
			id: tab.id,
			title: tab.title,
			kind: tab.content.kind,
			projectId: tab.projectId,
			settingsSection:
				tab.content.kind === "settings" ? tab.content.section : null,
			toolMode: tab.content.kind === "tool" ? tab.content.mode : null,
			minimized: tab.minimized,
		});
		const activeTab = auxiliary.open ? auxiliary.activeTab : null;
		const surface: WorkspaceSurface = !activeTab
			? "chat"
			: activeTab.selectedFile
				? "artifact"
				: activeTab.content.kind;
		return {
			schemaVersion: WORKSPACE_CONTEXT_SCHEMA_VERSION,
			surface,
			threadProjectId: activeProject?.id ?? null,
			activeTab: activeTab ? toContextTab(activeTab) : null,
			activeArtifact: activeTab?.selectedFile
				? {
						id: activeTab.selectedFile.id,
						documentId: activeTab.selectedFile.documentId ?? null,
						name: activeTab.selectedFile.name,
						kind: activeTab.selectedFile.kind,
						version: activeTab.selectedFile.version ?? null,
						editable: activeTab.selectedFile.editable,
					}
				: null,
			openTabs: auxiliary.session.tabs.slice(0, 20).map(toContextTab),
		};
	}, [
		activeProject?.id,
		auxiliary.activeTab,
		auxiliary.open,
		auxiliary.session.tabs,
	]);

	usePublishWorkspaceContext(workspaceContext);

	useEffect(() => {
		const projectId = activeThread?.custom?.projectId;
		if (typeof projectId !== "string" || projectId.trim() === "") {
			setActiveProject(null);
			return;
		}
		const project = projects.find(
			(candidate) => candidate.id === projectId,
		) ?? {
			id: projectId,
			name: activeThread?.title?.trim() || "Проект",
		};
		setActiveProject(project);
	}, [activeThread?.custom?.projectId, activeThread?.title, projects]);

	useAssistantInstructions(
		`You are Kolibri, an AI assistant inside a commercial project workspace.
The application has one persistent shell and one shared composer. The central Canvas displays either the conversation or the currently selected product surface; tools and artifacts appear only when requested.
Always use the published workspace context to identify the active surface, project, task, and artifact before acting on the user's message.
Treat drafts, marketplace offers, prices, contracts, calculations, and external mutations as unapproved until their visible server-backed state confirms otherwise.
Preserve project, artifact version, source, capture date, and user approval boundaries.`,
	);

	useAssistantContext({
		getContext: () =>
			[
				activeProject
					? `Active project: ${activeProject.name} (${activeProject.id}).`
					: "Active project: none.",
				`Active workspace surface: ${workspaceContext.surface}.`,
				`Active Canvas state: ${
					workspaceContext.activeTab?.kind ?? "conversation"
				}.`,
				auxiliary.activeFile
					? `Active artifact: ${auxiliary.activeFile.name}; version: ${auxiliary.activeFile.version ?? "unknown"}.`
					: "Active artifact: none.",
			].join("\n"),
	});

	const switchToProjectThread = useCallback(
		(projectId: string) => {
			const state = aui.threads().getState();
			const linkedThread = state.threadItems.find(
				(thread) => thread.custom?.projectId === projectId,
			);
			if (linkedThread && linkedThread.id !== state.mainThreadId) {
				void aui.threads().switchToThread(linkedThread.id);
			}
		},
		[aui],
	);

	const openChat = useCallback(() => auxiliary.dismiss(), [auxiliary]);

	const openProject = useCallback(
		(project: WorkspaceProject) => {
			switchToProjectThread(project.id);
			setActiveProject(project);
			auxiliary.openProject(project);
		},
		[auxiliary, switchToProjectThread],
	);

	const selectProjectInCanvas = useCallback(
		(project: WorkspaceProject) => {
			switchToProjectThread(project.id);
			setActiveProject(project);
			auxiliary.selectProject(project);
		},
		[auxiliary, switchToProjectThread],
	);

	const openPrimaryFile = useCallback(
		(file: WorkspaceFile) => {
			const project = file.projectId
				? projects.find((candidate) => candidate.id === file.projectId)
				: null;
			if (file.projectId) switchToProjectThread(file.projectId);
			if (project) setActiveProject(project);
			auxiliary.openFile(file);
		},
		[auxiliary, projects, switchToProjectThread],
	);

	const openPrimaryFiles = useCallback(() => {
		auxiliary.openFiles({
			projectId: activeProject?.id ?? null,
			title: activeProject?.name
				? `Документы · ${activeProject.name}`
				: "Документы",
		});
	}, [activeProject, auxiliary]);

	const openSettings = useCallback(
		(section: ProfileSettingsSection = "general") => {
			if (
				auxiliary.activeTab?.content.kind === "settings" &&
				auxiliary.activeTab.content.section === section
			) {
				setCommandPaletteOpen(false);
				return;
			}

			auxiliary.openSettings(section);
			setCommandPaletteOpen(false);
		},
		[auxiliary.activeTab, auxiliary.openSettings],
	);

	const accountDestinationRef = useRef<string | null>(null);
	const accountAlreadyOpenedAsBilling =
		auxiliary.activeTab?.content.kind === "settings" &&
		auxiliary.activeTab.content.section === "billing";

	useEffect(() => {
		const destination = new URL(window.location.href).searchParams.get(
			"account",
		);
		if (destination === null) {
			accountDestinationRef.current = null;
			return;
		}
		if (accountDestinationRef.current === destination) return;
		accountDestinationRef.current = destination;

		if (destination === "billing" && !accountAlreadyOpenedAsBilling) {
			openSettings("billing");
		}
	}, [accountAlreadyOpenedAsBilling, openSettings]);

	useEffect(() => {
		const openModels = () => openSettings("ai-models");
		window.addEventListener(KOLIBRI_OPEN_MODEL_SETTINGS_EVENT, openModels);
		return () =>
			window.removeEventListener(KOLIBRI_OPEN_MODEL_SETTINGS_EVENT, openModels);
	}, [openSettings]);

	useEffect(() => {
		const activateTask = (event: Event) => {
			const detail = event instanceof CustomEvent ? event.detail : null;
			if (!isActivateAgentTaskDetail(detail)) return;
			void (async () => {
				try {
					await aui.threads().switchToThread(detail.threadId);
					setActiveComposerTask({
						runId: detail.runId,
						threadId: detail.threadId,
					});
					window.requestAnimationFrame(() => {
						document
							.querySelector<HTMLElement>(
								'[data-slot="workspace-context-composer"] textarea, [data-slot="workspace-context-composer"] [contenteditable="true"]',
							)
							?.focus();
					});
				} catch {
					setActiveComposerTask(null);
				}
			})();
		};
		window.addEventListener(KOLIBRI_ACTIVATE_AGENT_TASK_EVENT, activateTask);
		return () =>
			window.removeEventListener(
				KOLIBRI_ACTIVATE_AGENT_TASK_EVENT,
				activateTask,
			);
	}, [aui]);

	useEffect(() => {
		if (!settingsCanvasOpen) setActiveComposerTask(null);
	}, [settingsCanvasOpen]);

	useDesktopWorkspaceShortcuts({
		onOpenTool: auxiliary.openTool,
		onToggleCommandPalette: () => setCommandPaletteOpen((open) => !open),
		onToggleNavigation: toggleNavigation,
	});

	const auxiliaryCanvas = (
		<DesktopAuxiliaryCanvas
			catalogState={catalogState}
			controller={auxiliary}
			onSelectProject={selectProjectInCanvas}
			onRefresh={() => void refresh()}
			projects={projects}
			workspaceFiles={workspaceFiles}
		/>
	);

	const activeDestination = !auxiliary.open
		? "chat"
		: auxiliary.activeTab?.content.kind === "projects"
			? "projects"
			: auxiliary.activeTab?.content.kind === "references"
				? "references"
				: auxiliary.activeTab?.content.kind === "files"
					? "documents"
					: "chat";
	// The center header belongs to the conversation. Auxiliary artifacts have
	// their own canvas frame header and must not replace the active thread title.
	const currentTitle = activeThread?.title?.trim() ?? "Новая задача";

	return (
		<DesktopWorkspaceView
			activeDestination={activeDestination}
			activeProject={activeProject}
			auxiliary={auxiliary}
			auxiliaryCanvas={auxiliaryCanvas}
			commandPaletteOpen={commandPaletteOpen}
			composerContextOverride={
				activeComposerTask ? `Задача · ${activeComposerTask.runId}` : undefined
			}
			currentTitle={currentTitle}
			navigationOpen={navigationOpen}
			onNewTask={() => {
				openChat();
				void aui.threads().switchToNewThread();
			}}
			onOpenSettings={openSettings}
			onOpenChat={openChat}
			onOpenDocuments={openPrimaryFiles}
			onOpenFile={openPrimaryFile}
			onOpenProject={openProject}
			onOpenProjects={() => {
				auxiliary.openProjects();
			}}
			onOpenReferences={() => {
				auxiliary.openReferences();
			}}
			onPaletteOpenChange={setCommandPaletteOpen}
			onSelectThread={(threadId) => {
				openChat();
				void aui.threads().switchToThread(threadId);
			}}
			onToggleNavigation={toggleNavigation}
			primaryContent={auxiliary.primaryOpen ? auxiliaryCanvas : null}
			primaryOpen={auxiliary.primaryOpen}
			projects={projects}
			threads={threadItems.filter((thread) => thread.status === "regular")}
			workspaceFiles={workspaceFiles}
		/>
	);
}
