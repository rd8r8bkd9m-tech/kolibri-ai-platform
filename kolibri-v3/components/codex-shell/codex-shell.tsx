"use client";

import "./codex-shell.css";

import { useCallback, useMemo } from "react";

import { DesktopAuxiliaryCanvas } from "@/components/kolibri-shell/desktop-workspace/desktop-auxiliary-canvas";
import { useAuxiliaryCanvas } from "@/components/kolibri-shell/desktop-workspace/use-auxiliary-canvas";
import { useWorkspaceDocumentCatalog } from "@/components/kolibri-shell/desktop-workspace/use-workspace-document-catalog";
import type { WorkspaceProject } from "@/lib/workspace-types";

import { CodexMain } from "./codex-main";
import { CodexSidebar } from "./codex-sidebar";

export function CodexShell() {
	const {
		files: workspaceFiles,
		refresh,
		state: catalogState,
	} = useWorkspaceDocumentCatalog();

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

	const auxiliary = useAuxiliaryCanvas({
		activeProject: null,
		onInteraction: () => undefined,
		workspaceFiles,
	});

	const toggleContext = useCallback(() => {
		if (auxiliary.open) {
			auxiliary.close();
		} else {
			auxiliary.openFiles();
		}
	}, [auxiliary]);

	return (
		<div
			className="codex-theme flex h-dvh w-full overflow-hidden bg-(--color-surface) text-(--color-text-foreground)"
			style={{ fontFamily: "var(--font-sans-default)" }}
		>
			<CodexSidebar onOpenSettings={auxiliary.openSettings} />
			<CodexMain
				onOpenAccount={() => auxiliary.openSettings("profile")}
				onOpenContextPanel={toggleContext}
				contextOpen={auxiliary.open}
			/>
			{auxiliary.open ? (
				<aside className="h-full w-[480px] max-w-[60vw] shrink-0 border-l border-(--color-border) bg-(--color-surface)">
					<DesktopAuxiliaryCanvas
						catalogState={catalogState}
						controller={auxiliary}
						onSelectProject={auxiliary.selectProject}
						onRefresh={refresh}
						projects={projects}
						workspaceFiles={workspaceFiles}
					/>
				</aside>
			) : null}
		</div>
	);
}
