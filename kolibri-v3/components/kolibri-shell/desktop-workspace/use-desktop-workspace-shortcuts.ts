"use client";

import { useEffect } from "react";
import type { ContextPanelMode } from "@/components/kolibri-workspace/context-panel";

export function useDesktopWorkspaceShortcuts({
	onOpenTool,
	onToggleCommandPalette,
	onToggleNavigation,
}: {
	onOpenTool: (mode: ContextPanelMode) => void;
	onToggleCommandPalette: () => void;
	onToggleNavigation: () => void;
}) {
	useEffect(() => {
		const handleShortcut = (event: KeyboardEvent) => {
			const target = event.target;
			if (
				target instanceof HTMLElement &&
				(target.isContentEditable ||
					target.matches("input, textarea, select, [role='textbox']"))
			) {
				return;
			}

			const key = event.key.toLocaleLowerCase("en-US");
			const command = event.metaKey || event.ctrlKey;
			if (command && key === "k" && !event.altKey && !event.shiftKey) {
				event.preventDefault();
				onToggleCommandPalette();
			} else if (command && key === "b" && !event.altKey) {
				event.preventDefault();
				onToggleNavigation();
			} else if (command && key === "p" && !event.altKey) {
				event.preventDefault();
				onOpenTool("files");
			} else if (command && key === "t" && !event.altKey) {
				event.preventDefault();
				onOpenTool("browser");
			} else if (event.ctrlKey && key === "`" && !event.altKey) {
				event.preventDefault();
				onOpenTool("terminal");
			} else if (event.ctrlKey && event.shiftKey && key === "g") {
				event.preventDefault();
				onOpenTool("review");
			}
		};

		window.addEventListener("keydown", handleShortcut);
		return () => window.removeEventListener("keydown", handleShortcut);
	}, [onOpenTool, onToggleCommandPalette, onToggleNavigation]);
}
