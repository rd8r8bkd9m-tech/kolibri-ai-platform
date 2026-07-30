import { useEffect } from "react";
import { ACTIVE_PROJECT_STORAGE_KEY, PROJECTS_STORAGE_KEY } from "../app/constants";
import { readProjects } from "../app/utils";
import { recoverInterruptedProjects } from "./projectMessageRecovery.js";
import { createProjectStoreState } from "./projectStoreModel";

export function initialProjectState() {
  const projects = readProjects();
  let saved = "";
  try {
    saved = globalThis.localStorage?.getItem(ACTIVE_PROJECT_STORAGE_KEY) || "";
  } catch {
    // Storage can be unavailable in private browsing; in-memory state remains valid.
  }
  return createProjectStoreState(projects, saved);
}

export function useProjectCache(state) {
  useEffect(() => {
    try {
      globalThis.localStorage?.setItem(
        PROJECTS_STORAGE_KEY,
        JSON.stringify(recoverInterruptedProjects(state.projects)),
      );
    } catch {
      // Keep the current session functional when persistent storage is blocked.
    }
  }, [state.projects]);

  useEffect(() => {
    try {
      if (state.activeProjectId) globalThis.localStorage?.setItem(ACTIVE_PROJECT_STORAGE_KEY, state.activeProjectId);
      else globalThis.localStorage?.removeItem(ACTIVE_PROJECT_STORAGE_KEY);
    } catch {
      // Keep the current session functional when persistent storage is blocked.
    }
  }, [state.activeProjectId]);
}
