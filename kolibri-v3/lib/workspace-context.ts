export const WORKSPACE_CONTEXT_SCHEMA_VERSION = "1.0" as const;

export type WorkspaceSurface =
	| "chat"
	| "settings"
	| "projects"
	| "references"
	| "files"
	| "artifact"
	| "tool"
	| "launcher";

export type WorkspaceContextTab = {
	id: string;
	title: string;
	kind: Exclude<WorkspaceSurface, "chat" | "artifact">;
	projectId: string | null;
	settingsSection: string | null;
	toolMode: string | null;
	minimized: boolean;
};

export type WorkspaceContextArtifact = {
	id: string;
	documentId: string | null;
	name: string;
	kind: string;
	version: number | null;
	editable: boolean;
};

export type WorkspaceContextV1 = {
	schemaVersion: typeof WORKSPACE_CONTEXT_SCHEMA_VERSION;
	surface: WorkspaceSurface;
	threadProjectId: string | null;
	activeTab: WorkspaceContextTab | null;
	activeArtifact: WorkspaceContextArtifact | null;
	openTabs: readonly WorkspaceContextTab[];
};
