import type { LucideIcon } from "lucide-react";
import {
	FileText,
	FolderKanban,
	LibraryBig,
} from "lucide-react";
import type { WorkspaceFile, WorkspaceProject } from "@/lib/workspace-types";

export type WorkspaceSidebarDestination =
	| "projects"
	| "documents"
	| "references";

export const WORKSPACE_PROJECTS: readonly WorkspaceProject[] = [];

export type ProjectContentSection =
	| "all"
	| "documents"
	| "contracts"
	| "estimates"
	| "drawings"
	| "attachments";

export type WorkspaceSidebarProps = {
	activeDestination?: "chat" | WorkspaceSidebarDestination;
	className?: string;
	isOverlay?: boolean;
	closeOnThreadSelect?: boolean;
	onOpenChat?: () => void;
	onOpenDocuments?: () => void;
	onOpenFile?: (file: WorkspaceFile) => void;
	onOpenAiModels?: () => void;
	onOpenProfileSettings?: () => void;
	onOpenProject?: (project: WorkspaceProject) => void;
	onOpenProjects?: () => void;
	onOpenReferenceCatalog?: () => void;
	onRequestClose?: () => void;
	projects?: readonly WorkspaceProject[];
	workspaceFiles?: readonly WorkspaceFile[];
};

export type SidebarNavigationItem = {
	id: WorkspaceSidebarDestination;
	icon: LucideIcon;
	label: string;
};

export const NAVIGATION_ITEMS: readonly SidebarNavigationItem[] = [
	{ id: "projects", icon: FolderKanban, label: "Проекты" },
	{ id: "documents", icon: FileText, label: "Документы" },
	{ id: "references", icon: LibraryBig, label: "Справочники" },
] as const;
