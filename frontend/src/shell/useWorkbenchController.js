import { useCallback, useEffect, useReducer } from "react";
import { WORKSPACE_STORAGE_KEY } from "../app/constants";
import { makeId, readWorkspace } from "../app/utils";
import { initialWorkbench, workbenchReducer } from "../workbench/reducer";
import { estimateWindow, isMaterializedArtifact, materializedArtifacts, projectWindow } from "./projectModel";

function projectArtifacts(projects) {
  return projects.flatMap((project) => materializedArtifacts(project.artifacts));
}

export function useWorkbenchController({ projects, setActiveProjectId }) {
  const [workbench, dispatch] = useReducer(workbenchReducer, initialWorkbench, readWorkspace);

  const openProject = useCallback((project, maximized = false) => {
    if (!project) return;
    dispatch({ type: "OPEN", window: projectWindow(project, maximized) });
    setActiveProjectId(project.id);
  }, [setActiveProjectId]);

  const activateProject = useCallback((project) => {
    if (!project) return;
    setActiveProjectId(project.id);
    dispatch({ type: "DEACTIVATE", id: "projects-window" });
  }, [setActiveProjectId]);

  const openEstimate = useCallback((projectId, title) => {
    dispatch({ type: "OPEN", window: estimateWindow(projectId, title) });
  }, []);

  const openSystemApp = useCallback((app) => {
    const isProjects = app === "projects";
    dispatch({
      type: "OPEN",
      window: {
        id: isProjects ? "projects-window" : "files-window",
        kind: isProjects ? "projects" : "files",
        title: isProjects ? "История" : "Файлы",
        statusLabel: isProjects ? "Сохранённые проекты" : "Проверенные артефакты",
        items: isProjects ? projects : projectArtifacts(projects),
      },
    });
  }, [projects]);

  const openArtifact = useCallback((projectId, artifact) => {
    if (!isMaterializedArtifact(artifact)) return;
    const isPdf = artifact.media_type === "application/pdf" || artifact.deliverable_type === "pdf";
    const isImage = String(artifact.media_type || "").startsWith("image/") || artifact.deliverable_type === "image";
    dispatch({
      type: "OPEN",
      window: {
        id: `artifact:${artifact.reference_sha256 || artifact.id || makeId("artifact")}`,
        kind: isPdf ? "pdf" : isImage ? "image" : "response",
        title: artifact.display_name || artifact.name || artifact.kind || "Артефакт",
        parentProjectId: projectId,
        status: "completed",
        statusLabel: "Проверенный файл",
        artifacts: [artifact],
        ...((isPdf || isImage) ? { artifact } : {}),
      },
    });
  }, []);

  const openCanvas = useCallback((projectId, canvas) => {
    dispatch({
      type: "OPEN",
      window: {
        id: `canvas-window:${canvas.id}`,
        kind: "canvas",
        title: canvas.title || "Результат",
        statusLabel: "Редактор проекта",
        parentProjectId: projectId,
        canvasId: canvas.id,
      },
    });
  }, []);

  const focusWindow = useCallback((windowState) => {
    if (windowState.kind === "workspace" && windowState.payload?.projectId) {
      setActiveProjectId(windowState.payload.projectId);
    }
  }, [setActiveProjectId]);

  useEffect(() => {
    dispatch({ type: "UPDATE", id: "projects-window", window: { items: projects } });
    dispatch({ type: "UPDATE", id: "files-window", window: { items: projectArtifacts(projects) } });
  }, [projects]);

  useEffect(() => {
    globalThis.localStorage.setItem(WORKSPACE_STORAGE_KEY, JSON.stringify(workbench));
  }, [workbench]);

  return {
    activateProject,
    dispatch,
    focusWindow,
    openArtifact,
    openCanvas,
    openEstimate,
    openProject,
    openSystemApp,
    workbench,
  };
}
