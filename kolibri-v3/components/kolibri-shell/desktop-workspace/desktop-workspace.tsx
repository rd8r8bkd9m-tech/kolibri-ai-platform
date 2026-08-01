"use client";

import {
	useAssistantContext,
	useAssistantInstructions,
	useAui,
	useAuiState,
} from "@assistant-ui/react";
import { useCallback, useEffect, useMemo, useState } from "react";
import type { ProfileSettingsSection } from "@/components/kolibri-shell/profile-settings-surface";
import type { WorkspaceFile } from "@/components/kolibri-workspace";
import { KOLIBRI_OPEN_MODEL_SETTINGS_EVENT } from "@/lib/workspace-events";
import type { WorkspaceProject } from "@/lib/workspace-types";
import {
	primarySurfaceDestination,
	type DesktopPrimarySurface,
} from "./types";
import { DesktopAuxiliaryCanvas } from "./desktop-auxiliary-canvas";
import { DesktopWorkspaceView } from "./desktop-workspace-view";
import { PrimaryWorkspaceSurface } from "./primary-workspace-surface";
import { useAuxiliaryCanvas } from "./use-auxiliary-canvas";
import { useDesktopWorkspaceShortcuts } from "./use-desktop-workspace-shortcuts";
import { useWorkspaceDocumentCatalog } from "./use-workspace-document-catalog";

function findCurrentFile(files: readonly WorkspaceFile[], id: string | null) {
	if (!id) return null;
	return files.find((file) => file.id === id) ?? null;
}

export function DesktopWorkspace() {
	const aui = useAui();
	const { files: workspaceFiles, refresh, state: catalogState } =
		useWorkspaceDocumentCatalog();
	const threadItems = useAuiState((state) => state.threads.threadItems);
	const activeThreadId = useAuiState((state) => state.threads.mainThreadId);
	const activeThread = threadItems.find((thread) => thread.id === activeThreadId);

	const [navigationOpen, setNavigationOpen] = useState(true);
	const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);
	const [activeProject, setActiveProject] = useState<WorkspaceProject | null>(
		null,
	);
	const [primarySurface, setPrimarySurface] =
		useState<DesktopPrimarySurface | null>(null);
	const [accountOpen, setAccountOpen] = useState(false);
	const [accountSection, setAccountSection] =
		useState<ProfileSettingsSection>("general");

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

	const closeAccount = useCallback(() => setAccountOpen(false), []);
	const auxiliary = useAuxiliaryCanvas({
		activeProject,
		onInteraction: closeAccount,
		workspaceFiles,
	});
	const primaryFile =
		primarySurface?.kind === "files"
			? findCurrentFile(workspaceFiles, primarySurface.selectedFileId)
			: null;

	useEffect(() => {
		const projectId = activeThread?.custom?.projectId;
		if (typeof projectId !== "string" || projectId.trim() === "") {
			setActiveProject(null);
			return;
		}
		const project = projects.find((candidate) => candidate.id === projectId) ?? {
			id: projectId,
			name: activeThread?.title?.trim() || "Проект",
		};
		setActiveProject(project);
	}, [activeThread?.custom?.projectId, activeThread?.title, projects]);

	useAssistantInstructions(
		`You are Kolibri, an AI assistant inside a commercial project workspace.
The left sidebar is the primary navigation, the center is the persistent conversation, and the optional right canvas contains the explicitly selected tool or artifact.
Treat drafts, marketplace offers, prices, contracts, calculations, and external mutations as unapproved until their visible server-backed state confirms otherwise.
Preserve project, artifact version, source, capture date, and user approval boundaries.`,
	);

	useAssistantContext({
		getContext: () =>
			[
				activeProject
					? `Active project: ${activeProject.name} (${activeProject.id}).`
					: "Active project: none.",
				`Primary surface: ${primarySurface?.kind ?? "chat"}.`,
				`Auxiliary canvas: ${
					auxiliary.open
						? (auxiliary.activeTool ?? auxiliary.activeTab?.content.kind)
						: "closed"
				}.`,
				auxiliary.activeFile
					? `Auxiliary artifact: ${auxiliary.activeFile.name}; version: ${auxiliary.activeFile.version ?? "unknown"}.`
					: "Auxiliary artifact: none.",
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

	const openChat = useCallback(() => {
		setPrimarySurface(null);
		setAccountOpen(false);
	}, []);

	const openProject = useCallback(
		(project: WorkspaceProject) => {
			switchToProjectThread(project.id);
			setActiveProject(project);
			setPrimarySurface({
				category: "all",
				kind: "files",
				projectId: project.id,
				selectedFileId: null,
				title: project.name,
			});
			setAccountOpen(false);
		},
		[switchToProjectThread],
	);

	const openPrimaryFile = useCallback(
		(file: WorkspaceFile) => {
			const project = file.projectId
				? projects.find((candidate) => candidate.id === file.projectId)
				: null;
			if (file.projectId) switchToProjectThread(file.projectId);
			if (project) setActiveProject(project);
			setPrimarySurface({
				category: file.category,
				kind: "files",
				projectId: file.projectId ?? null,
				selectedFileId: file.id,
				title: file.name,
			});
			setAccountOpen(false);
		},
		[projects, switchToProjectThread],
	);

	const openPrimaryFiles = useCallback(() => {
		setPrimarySurface({
			category: "all",
			kind: "files",
			projectId: activeProject?.id ?? null,
			selectedFileId: null,
			title: activeProject?.name
				? `Документы · ${activeProject.name}`
				: "Документы",
		});
		setAccountOpen(false);
	}, [activeProject]);

	const openAccount = useCallback(
		(section: ProfileSettingsSection = "general") => {
			setAccountSection(section);
			setAccountOpen(true);
			setCommandPaletteOpen(false);
		},
		[],
	);

	useEffect(() => {
		const destination = new URL(window.location.href).searchParams.get("account");
		if (destination === "billing") openAccount("billing");
	}, [openAccount]);

	useEffect(() => {
		const openModels = () => openAccount("ai-models");
		window.addEventListener(KOLIBRI_OPEN_MODEL_SETTINGS_EVENT, openModels);
		return () =>
			window.removeEventListener(KOLIBRI_OPEN_MODEL_SETTINGS_EVENT, openModels);
	}, [openAccount]);

	useDesktopWorkspaceShortcuts({
		onOpenTool: auxiliary.openTool,
		onToggleCommandPalette: () => setCommandPaletteOpen((open) => !open),
		onToggleNavigation: () => setNavigationOpen((open) => !open),
	});

	const auxiliaryCanvas = (
		<DesktopAuxiliaryCanvas
			catalogState={catalogState}
			controller={auxiliary}
			onOpenSettings={() => openAccount("integrations")}
			onRefresh={() => void refresh()}
			projects={projects}
			workspaceFiles={workspaceFiles}
		/>
	);

	const primaryContent = primarySurface ? (
		<PrimaryWorkspaceSurface
			activeProject={activeProject}
			catalogState={catalogState}
			onOpenChat={openChat}
			onOpenProject={openProject}
			onRetry={() => void refresh()}
			primaryFile={primaryFile}
			projects={projects}
			setSurface={setPrimarySurface}
			surface={primarySurface}
			workspaceFiles={workspaceFiles}
		/>
	) : null;
	const activeDestination = primarySurfaceDestination(primarySurface);
	const currentTitle =
		primaryFile?.name ??
		primarySurface?.title ??
		activeThread?.title?.trim() ??
		"Новая задача";

	return (
		<DesktopWorkspaceView
			accountOpen={accountOpen}
			accountSection={accountSection}
			activeDestination={activeDestination}
			activeProject={activeProject}
			auxiliary={auxiliary}
			auxiliaryCanvas={auxiliaryCanvas}
			commandPaletteOpen={commandPaletteOpen}
			currentTitle={currentTitle}
			navigationOpen={navigationOpen}
			onAccountSectionChange={setAccountSection}
			onCloseAccount={closeAccount}
			onNewTask={() => {
				void aui.threads().switchToNewThread();
				openChat();
			}}
			onOpenAccount={openAccount}
			onOpenChat={openChat}
			onOpenDocuments={openPrimaryFiles}
			onOpenFile={openPrimaryFile}
			onOpenProject={openProject}
			onOpenProjects={() => {
				setPrimarySurface({ kind: "projects", title: "Проекты" });
				setAccountOpen(false);
			}}
			onOpenReferences={() => {
				setPrimarySurface({ kind: "references", title: "Справочники" });
				setAccountOpen(false);
			}}
			onPaletteOpenChange={setCommandPaletteOpen}
			onSelectThread={(threadId) => {
				void aui.threads().switchToThread(threadId);
				openChat();
			}}
			onToggleNavigation={() => setNavigationOpen((open) => !open)}
			primaryContent={primaryContent}
			primaryOpen={primarySurface !== null}
			projects={projects}
			threads={threadItems.filter((thread) => thread.status === "regular")}
			workspaceFiles={workspaceFiles}
		/>
	);
}
