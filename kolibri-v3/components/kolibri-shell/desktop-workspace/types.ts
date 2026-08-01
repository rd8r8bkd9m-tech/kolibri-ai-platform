import type { WorkspaceFileCategory } from "@/components/kolibri-workspace";

export type DesktopPrimarySurface =
	| { kind: "projects"; title: "Проекты" }
	| { kind: "references"; title: "Справочники" }
	| {
			category: WorkspaceFileCategory;
			kind: "files";
			projectId: string | null;
			selectedFileId: string | null;
			title: string;
	  };

export function primarySurfaceDestination(
	surface: DesktopPrimarySurface | null,
) {
	if (!surface) return "chat" as const;
	if (surface.kind === "projects") return "projects" as const;
	if (surface.kind === "references") return "references" as const;
	return "documents" as const;
}
