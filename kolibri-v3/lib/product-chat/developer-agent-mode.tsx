"use client";

import {
	createContext,
	useContext,
	type Dispatch,
	type SetStateAction,
} from "react";

export const DEVELOPER_ACCESS_MODES = ["standard", "auto", "full"] as const;

export type DeveloperAccessMode = (typeof DEVELOPER_ACCESS_MODES)[number];

const DEVELOPER_ACCESS_MODE_KEY = "kolibri.ui.developer-access-mode";

/**
 * Developer access mode is a local UI preference (like theme choice), not a
 * history source of truth. Product Chat history itself stays server-backed.
 */
export const readDeveloperAccessMode = (): DeveloperAccessMode => {
	// Dev-режим (coding-агент) выключен по умолчанию: смета и чат идут в
	// "standard" и работают на chat-only runtime (Qwen). Кодинг включается
	// пользователем явно через переключатель.
	if (typeof globalThis.localStorage === "undefined") return "standard";
	const saved = globalThis.localStorage.getItem(DEVELOPER_ACCESS_MODE_KEY);
	return saved === "standard" || saved === "auto" || saved === "full"
		? saved
		: "standard";
};

export const persistDeveloperAccessMode = (
	next: DeveloperAccessMode,
): void => {
	try {
		globalThis.localStorage?.setItem(DEVELOPER_ACCESS_MODE_KEY, next);
	} catch {
		// Storage can be blocked; the in-memory choice still applies.
	}
};

export type DeveloperAgentModeContextValue = {
	readonly available: boolean;
	readonly mode: DeveloperAccessMode;
	readonly setMode: Dispatch<SetStateAction<DeveloperAccessMode>>;
	readonly enabled: boolean;
	readonly setEnabled: Dispatch<SetStateAction<boolean>>;
};

export const DeveloperAgentModeContext =
	createContext<DeveloperAgentModeContextValue>({
		available: false,
		mode: "standard",
		setMode: () => undefined,
		enabled: false,
		setEnabled: () => undefined,
	});

export const useDeveloperAgentMode = () =>
	useContext(DeveloperAgentModeContext);
