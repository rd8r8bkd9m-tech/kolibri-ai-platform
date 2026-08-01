"use client";

import type { Dispatch, SetStateAction } from "react";
import {
	CanvasWorkspace,
	type WorkspaceFile,
} from "@/components/kolibri-workspace";
import { ProjectsOverview } from "@/components/kolibri-workspace/projects-overview";
import { ReferenceCatalog } from "@/components/kolibri-workspace/reference-catalog";
import type { WorkspaceCatalogLoadState } from "@/lib/workspace-documents";
import type { WorkspaceProject } from "@/lib/workspace-types";
import type { DesktopPrimarySurface } from "./types";

const FILE_SECTION_TITLES = {
	all: "Все файлы",
	attachments: "Вложения",
	contracts: "Договоры",
	documents: "Документы",
	drawings: "Чертежи",
	estimates: "Сметы",
} as const;

export type PrimaryWorkspaceSurfaceProps = {
	activeProject: WorkspaceProject | null;
	catalogState: WorkspaceCatalogLoadState;
	onOpenChat: () => void;
	onOpenProject: (project: WorkspaceProject) => void;
	onRetry: () => void;
	primaryFile: WorkspaceFile | null;
	projects: readonly WorkspaceProject[];
	setSurface: Dispatch<SetStateAction<DesktopPrimarySurface | null>>;
	surface: DesktopPrimarySurface;
	workspaceFiles: readonly WorkspaceFile[];
};

export function PrimaryWorkspaceSurface({
	activeProject,
	catalogState,
	onOpenChat,
	onOpenProject,
	onRetry,
	primaryFile,
	projects,
	setSurface,
	surface,
	workspaceFiles,
}: PrimaryWorkspaceSurfaceProps) {
	if (surface.kind === "projects") {
		return (
			<ProjectsOverview
				activeProjectId={activeProject?.id}
				catalogState={catalogState}
				onOpenProject={onOpenProject}
				onRetry={onRetry}
				projects={projects}
			/>
		);
	}
	if (surface.kind === "references") return <ReferenceCatalog />;

	const project = surface.projectId
		? projects.find((candidate) => candidate.id === surface.projectId)
		: activeProject;
	const scopedFiles = surface.projectId
		? workspaceFiles.filter((file) => file.projectId === surface.projectId)
		: workspaceFiles;

	return (
		<CanvasWorkspace
			compactChrome
			fileCategory={surface.category}
			placement="primary"
			projectName={project?.name}
			selectedFile={primaryFile}
			surfaceMode="files"
			toolMode="files"
			workspaceCatalogState={catalogState}
			workspaceFiles={scopedFiles}
			onFilesBack={onOpenChat}
			onRetryWorkspaceCatalog={onRetry}
			onSelectedFileChange={(file) =>
				setSurface((current) =>
					current?.kind === "files"
						? {
								...current,
								category: file?.category ?? current.category,
								selectedFileId: file?.id ?? null,
								title:
									file?.name ??
									(project?.name
										? `${FILE_SECTION_TITLES[current.category]} · ${project.name}`
										: FILE_SECTION_TITLES[current.category]),
							}
						: current,
				)
			}
			onToolModeChange={(mode) => {
				if (mode === null) onOpenChat();
			}}
		/>
	);
}
