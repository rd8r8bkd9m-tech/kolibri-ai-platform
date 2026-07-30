import { useCallback, useEffect, useReducer, useRef } from "react";
import { createProject } from "../app/utils";
import { initialProjectState, useProjectCache } from "./useProjectCache";
import { projectStoreReducer, sameProjectSnapshot } from "./projectStoreModel";
import { useProjectRepositorySync } from "./useProjectRepositorySync";
import { useProjectRequestLifecycle } from "./useProjectRequestLifecycle";

function unchangedReplacement(projects, replacementProject) {
  if (!replacementProject) return null;
  const current = projects.find((project) => project.id === replacementProject.id);
  return current && sameProjectSnapshot(current, replacementProject) ? current : null;
}

export function useProjectStore() {
  const [state, dispatch] = useReducer(projectStoreReducer, undefined, initialProjectState);
  const stateRef = useRef(state);
  useEffect(() => {
    stateRef.current = state;
  }, [state]);
  const repository = useProjectRepositorySync(state, stateRef, dispatch);
  const requests = useProjectRequestLifecycle(dispatch);
  useProjectCache(state);

  const updateProject = useCallback((projectId, updater) => {
    dispatch({ type: "UPDATE_PROJECT", projectId, updater, updatedAt: new Date().toISOString() });
  }, []);

  const addProject = useCallback(() => {
    const project = createProject();
    dispatch({ type: "ADD_PROJECT", project, activate: false });
    repository.createProjectRemote(project);
    return project;
  }, [repository]);

  const deleteProject = useCallback((projectId) => {
    const project = stateRef.current.projects.find((item) => item.id === projectId);
    if (!project || stateRef.current.busyProjects[projectId]) return null;
    const replacementProject = stateRef.current.projects.length === 1 ? createProject() : null;
    const operationId = repository.mutationId("project-delete", project.id);
    const deletion = {
      project,
      index: stateRef.current.projects.findIndex((item) => item.id === projectId),
      wasActive: stateRef.current.activeProjectId === projectId,
      previousActiveProjectId: stateRef.current.activeProjectId,
      replacementProject,
      activeChanged: false,
      operationId,
    };
    dispatch({ type: "DELETE_PROJECT", projectId, replacementProject, operationId });
    repository.deleteProjectRemote(project, deletion, replacementProject);
    return project;
  }, [repository]);

  const undoDeleteProject = useCallback(() => {
    const deletion = stateRef.current.lastDeleted;
    if (!deletion) return null;
    const replacement = unchangedReplacement(stateRef.current.projects, deletion.replacementProject);
    dispatch({ type: "RESTORE_PROJECT" });
    repository.restoreProjectRemote(deletion, replacement);
    return deletion.project;
  }, [repository]);

  const dismissDeleteUndo = useCallback(() => dispatch({ type: "DISMISS_DELETION" }), []);
  const setActiveProjectId = useCallback((projectId) => dispatch({ type: "SET_ACTIVE_PROJECT", projectId }), []);

  return {
    activeProjectId: state.activeProjectId,
    addProject,
    ...requests,
    busyProjects: state.busyProjects,
    deleteProject,
    dismissDeleteUndo,
    ensureProjectRemote: repository.ensureProjectRemote,
    lastDeleted: state.lastDeleted,
    projects: state.projects,
    reconcileProjectRemote: repository.reconcileProjectRemote,
    setActiveProjectId,
    syncProjectMessage: repository.syncProjectMessage,
    undoDeleteProject,
    updateProject,
  };
}
