"use client";

import { useCallback, useEffect, useState } from "react";
import type { WorkspaceFile } from "@/components/kolibri-workspace";
import { useIdentity } from "@/lib/identity/provider";
import {
	parseWorkspaceDocuments,
	type WorkspaceCatalogLoadState,
} from "@/lib/workspace-documents";
import { KOLIBRI_DOCUMENTS_CHANGED_EVENT } from "@/lib/workspace-events";

export type WorkspaceDocumentCatalog = {
	files: WorkspaceFile[];
	refresh: () => Promise<void>;
	state: WorkspaceCatalogLoadState;
};

export function useWorkspaceDocumentCatalog(): WorkspaceDocumentCatalog {
	const identity = useIdentity();
	const [files, setFiles] = useState<WorkspaceFile[]>([]);
	const [state, setState] =
		useState<WorkspaceCatalogLoadState>("loading");

	const refresh = useCallback(async () => {
		if (identity.status !== "authenticated") {
			setFiles([]);
			setState("ready");
			return;
		}

		setState("loading");
		try {
			const response = await fetch("/api/v3/documents", {
				method: "GET",
				headers: { Accept: "application/json" },
				credentials: "same-origin",
				cache: "no-store",
			});
			if (!response.ok) {
				throw new Error(`Document catalog returned HTTP ${response.status}.`);
			}
			setFiles(parseWorkspaceDocuments(await response.json()));
			setState("ready");
		} catch {
			setState("error");
		}
	}, [identity.status]);

	useEffect(() => {
		void refresh();
	}, [refresh]);

	useEffect(() => {
		const handleDocumentsChanged = () => void refresh();
		window.addEventListener(
			KOLIBRI_DOCUMENTS_CHANGED_EVENT,
			handleDocumentsChanged,
		);
		return () =>
			window.removeEventListener(
				KOLIBRI_DOCUMENTS_CHANGED_EVENT,
				handleDocumentsChanged,
			);
	}, [refresh]);

	return { files, refresh, state };
}
