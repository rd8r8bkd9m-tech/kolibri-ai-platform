import { useCallback } from "react";

export function useProjectCommands({
  activeProjectId,
  addProject,
  executionModes,
  openCanvas,
  projects,
  setActiveProjectId,
  updateProject,
}) {
  const newProject = useCallback(() => {
    const project = addProject();
    setActiveProjectId(project.id);
  }, [addProject, setActiveProjectId]);

  const selectTool = useCallback((tool) => {
    const projectId = activeProjectId || projects[0]?.id;
    if (!projects.some((project) => project.id === projectId)) return;
    updateProject(projectId, { draftTool: tool, viewMode: "dialog" });
  }, [activeProjectId, projects, updateProject]);

  const setExecutionMode = useCallback((projectId, executionMode) => {
    if (!executionModes.includes(executionMode)) return;
    updateProject(projectId, { executionMode });
  }, [executionModes, updateProject]);

  const updateCanvas = useCallback((projectId, canvasId, patch) => {
    updateProject(projectId, (current) => ({
      ...current,
      canvases: (current.canvases || []).map((canvas) => canvas.id === canvasId ? { ...canvas, ...patch } : canvas),
    }));
  }, [updateProject]);

  const detachCanvas = useCallback((projectId, canvas) => {
    openCanvas(projectId, canvas);
  }, [openCanvas]);

  return { detachCanvas, newProject, selectTool, setExecutionMode, updateCanvas };
}
