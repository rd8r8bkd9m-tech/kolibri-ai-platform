"use client";

import { useEffect } from "react";
import type { ContextPanelMode } from "@/components/kolibri-workspace/context-panel";

export const KOLIBRI_GLOBAL_SAVE_EVENT = "kolibri:global-save";

export function useDesktopWorkspaceShortcuts({
	onEscape,
	onOpenTool,
	onToggleCommandPalette,
	onToggleNavigation,
}: {
	onEscape?: () => void;
	onOpenTool: (mode: ContextPanelMode) => void;
	onToggleCommandPalette: () => void;
	onToggleNavigation: () => void;
}) {
	useEffect(() => {
		const handleShortcut = (event: KeyboardEvent) => {
			const target = event.target;
			// IME/synthetic events can carry an undefined `key`; treat them as
			// non-shortcuts instead of crashing the workspace.
			if (typeof event.key !== "string") {
				return;
			}
			const key = event.key.toLocaleLowerCase("en-US");
			const command = event.metaKey || event.ctrlKey;
			
			if (command && key === "s" && !event.altKey && !event.shiftKey) {
				event.preventDefault();
				window.dispatchEvent(new CustomEvent(KOLIBRI_GLOBAL_SAVE_EVENT));
				return;
			}
			
			if (
				target instanceof HTMLElement &&
				(target.isContentEditable ||
					target.matches("input, textarea, select, [role='textbox']"))
			) {
				return;
			}

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
			} else if (key === "escape" && !command && !event.altKey) {
				// Redesign spec §6: Escape walks the canvas chain
				// fullscreen → docked → closed, then closes overlay navigation.
				onEscape?.();
			}
		};

		window.addEventListener("keydown", handleShortcut);
		return () => window.removeEventListener("keydown", handleShortcut);
	}, [onOpenTool, onToggleCommandPalette, onToggleNavigation]);
}
