import { useCallback, useEffect, useRef, useState } from "react";
import { ProjectRepository } from "../runtime/ProjectRepository";
import { sameProjectSnapshot } from "./projectStoreModel";

function projectSyncSignature(project) {
  return JSON.stringify([
    project.id,
    project.title,
    project.viewMode || "dialog",
    project.executionMode || "fast",
    project.draftTool || "",
  ]);
}

function mutationId(scope, localId) {
  const nonce = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${scope}-${localId}-${nonce}`;
}

export function useProjectRepositorySync(state, stateRef, dispatch) {
  const [ready, setReady] = useState(false);
  const [repository] = useState(() => new ProjectRepository());
  const deletionPromises = useRef(new Map());

  const bindRemoteProject = useCallback((projectId, remoteId) => {
    if (remoteId) dispatch({ type: "BIND_REMOTE_PROJECT", projectId, remoteId });
  }, [dispatch]);

  const ensureProjectRemote = useCallback(async (projectId, signal) => {
    const project = stateRef.current.projects.find((item) => item.id === projectId);
    if (!project) throw new Error("Проект больше не доступен.");
    const synchronized = await repository.ensureProject(project, signal);
    bindRemoteProject(projectId, synchronized.remoteId);
    return synchronized.remoteId;
  }, [bindRemoteProject, repository, stateRef]);

  const reconcileProjectRemote = useCallback(async (projectId, failedRemoteId, signal) => {
    const project = stateRef.current.projects.find((item) => item.id === projectId);
    if (!project) throw new Error("Проект больше не доступен.");
    const synchronized = await repository.reconcileProject(project, {
      failedRemoteId,
      signal,
    });
    bindRemoteProject(projectId, synchronized.remoteId);
    return synchronized.remoteId;
  }, [bindRemoteProject, repository, stateRef]);

  const syncProjectMessage = useCallback(async (projectId, message, options = {}) => {
    const project = stateRef.current.projects.find((item) => item.id === projectId);
    if (!project || !message) return null;
    const synchronized = await repository.syncMessage(project, message, options);
    dispatch({
      type: "BIND_REMOTE_MESSAGE",
      projectId,
      messageId: message.id,
      patch: {
        remoteId: synchronized.remoteId,
        ...(synchronized.responseId ? { responseId: synchronized.responseId } : {}),
        updatedAt: synchronized.updatedAt || new Date().toISOString(),
      },
    });
    bindRemoteProject(projectId, repository.remoteProjectId(project));
    return synchronized;
  }, [bindRemoteProject, dispatch, repository, stateRef]);

  const createProjectRemote = useCallback((project) => {
    repository.ensureProject(project)
      .then((synchronized) => bindRemoteProject(project.id, synchronized.remoteId))
      .catch(() => {});
  }, [bindRemoteProject, repository]);

  const deleteProjectRemote = useCallback((project, deletion, replacementProject) => {
    const pending = repository.removeProject(project, { operationId: deletion.operationId })
      .then(() => true)
      .catch(() => {
        dispatch({ type: "ROLLBACK_PROJECT_DELETE", deletion });
        const currentReplacement = replacementProject
          ? stateRef.current.projects.find((project) => project.id === replacementProject.id)
          : null;
        if (currentReplacement && sameProjectSnapshot(currentReplacement, replacementProject)) {
          repository.removeProject(currentReplacement, {
            operationId: mutationId("project-delete-rollback-replacement", replacementProject.id),
          }).catch(() => {});
        }
        return false;
      })
      .finally(() => deletionPromises.current.delete(project.id));
    deletionPromises.current.set(project.id, pending);
  }, [dispatch, repository, stateRef]);

  const restoreProjectRemote = useCallback((deletion, replacement) => {
    Promise.resolve(deletionPromises.current.get(deletion.project.id))
      .then(() => repository.restoreProject(deletion.project, {
        operationId: mutationId("project-restore", deletion.project.id),
      }))
      .then((synchronized) => bindRemoteProject(deletion.project.id, synchronized.remoteId))
      .catch(() => {});
    if (replacement) {
      repository.removeProject(replacement, {
        operationId: mutationId("project-delete-replacement", replacement.id),
      }).catch(() => {});
    }
  }, [bindRemoteProject, repository]);

  useEffect(() => {
    const controller = new AbortController();
    const baseProjects = stateRef.current.projects;
    const startedAt = Date.now();
    repository.hydrate(baseProjects, controller.signal)
      .then((projects) => {
        if (!controller.signal.aborted) dispatch({
          type: "RECONCILE_PROJECTS",
          projects,
          baseProjectIds: baseProjects.map((project) => project.id),
          startedAt,
        });
      })
      .catch(() => {})
      .finally(() => {
        if (!controller.signal.aborted) setReady(true);
      });
    return () => controller.abort();
  }, [dispatch, repository, stateRef]);

  const signature = state.projects.map(projectSyncSignature).join("|");
  useEffect(() => {
    if (!ready) return undefined;
    const timer = globalThis.setTimeout(() => {
      for (const project of stateRef.current.projects) {
        repository.updateProject(project)
          .then((synchronized) => bindRemoteProject(project.id, synchronized.remoteId))
          .catch(() => {});
      }
    }, 250);
    return () => globalThis.clearTimeout(timer);
  }, [bindRemoteProject, ready, repository, signature, stateRef]);

  return {
    createProjectRemote,
    deleteProjectRemote,
    ensureProjectRemote,
    mutationId,
    reconcileProjectRemote,
    restoreProjectRemote,
    syncProjectMessage,
  };
}
