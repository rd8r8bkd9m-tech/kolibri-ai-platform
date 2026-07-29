"use client";

import {
  createContext,
  useContext,
  type Dispatch,
  type SetStateAction,
} from "react";

export const DEVELOPER_ACCESS_MODES = [
  "standard",
  "auto",
  "full",
] as const;

export type DeveloperAccessMode =
  (typeof DEVELOPER_ACCESS_MODES)[number];

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
