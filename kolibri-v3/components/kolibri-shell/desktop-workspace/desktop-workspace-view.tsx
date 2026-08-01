"use client";

import type { ReactNode } from "react";
import { Thread } from "@/components/assistant-ui/thread";
import { KolibriPetHost } from "@/components/kolibri-shell/kolibri-pet";
import {
	type ProfileSettingsSection,
	ProfileSettingsSurface,
} from "@/components/kolibri-shell/profile-settings-surface";
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
	accountOpen,
	accountSection,
	activeDestination,
	activeProject,
	auxiliary,
	auxiliaryCanvas,
	commandPaletteOpen,
	currentTitle,
	navigationOpen,
	onAccountSectionChange,
	onCloseAccount,
	onNewTask,
	onOpenAccount,
	onOpenChat,
	onOpenDocuments,
	onOpenFile,
	onOpenProject,
	onOpenProjects,
	onOpenReferences,
	onPaletteOpenChange,
	onSelectThread,
	onToggleNavigation,
	primaryContent,
	primaryOpen,
	projects,
	threads,
	workspaceFiles,
}: {
	accountOpen: boolean;
	accountSection: ProfileSettingsSection;
	activeDestination: WorkspaceSidebarProps["activeDestination"];
	activeProject: WorkspaceProject | null;
	auxiliary: AuxiliaryCanvasController;
	auxiliaryCanvas: ReactNode;
	commandPaletteOpen: boolean;
	currentTitle: string;
	navigationOpen: boolean;
	onAccountSectionChange: (section: ProfileSettingsSection) => void;
	onCloseAccount: () => void;
	onNewTask: () => void;
	onOpenAccount: (section: ProfileSettingsSection) => void;
	onOpenChat: () => void;
	onOpenDocuments: () => void;
	onOpenFile: (file: WorkspaceFile) => void;
	onOpenProject: (project: WorkspaceProject) => void;
	onOpenProjects: () => void;
	onOpenReferences: () => void;
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
			onOpenAiModels={() => onOpenAccount("ai-models")}
			onOpenChat={onOpenChat}
			onOpenDocuments={onOpenDocuments}
			onOpenProfileSettings={() => onOpenAccount("general")}
			onOpenProjects={onOpenProjects}
			onOpenReferenceCatalog={onOpenReferences}
			onRequestClose={onToggleNavigation}
		/>
	);

	const chrome = (
		<>
			<WorkspaceCommandPalette
				contextPanelOpen={auxiliary.open}
				files={workspaceFiles}
				navigationOpen={navigationOpen}
				onNewTask={onNewTask}
				onOpenBrowser={() => auxiliary.openTool("browser")}
				onOpenChange={onPaletteOpenChange}
				onOpenDocuments={onOpenDocuments}
				onOpenProfile={() => onOpenAccount("general")}
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
			<KolibriPetHost />
		</>
	);

	return (
		<DesktopWorkspaceLayout
			account={
				<ProfileSettingsSurface
					activeSection={accountSection}
					onClose={onCloseAccount}
					onSectionChange={onAccountSectionChange}
				/>
			}
			accountOpen={accountOpen}
			auxiliary={auxiliaryCanvas}
			auxiliaryFullscreen={auxiliary.fullscreen}
			auxiliaryOpen={auxiliary.open}
			chat={
				<Thread
					onOpenAccount={() => onOpenAccount("general")}
					onOpenContextPanel={auxiliary.toggle}
					workspaceOpen={auxiliary.open}
				/>
			}
			chrome={chrome}
			header={
				<WorkspaceHeader
					activeProjectId={activeProject?.id}
					contextPanelOpen={auxiliary.open}
					navigationOpen={navigationOpen}
					onBack={primaryOpen ? onOpenChat : undefined}
					onOpenCommandPalette={() => onPaletteOpenChange(true)}
					onProjectSelect={onOpenProject}
					onToggleContextPanel={auxiliary.toggle}
					onToggleNavigation={onToggleNavigation}
					projectName={activeProject?.name}
					projects={projects}
					threadTitle={currentTitle}
				/>
			}
			navigation={navigation}
			navigationOpen={navigationOpen}
			primary={primaryContent}
			primaryOpen={primaryOpen}
		/>
	);
}
