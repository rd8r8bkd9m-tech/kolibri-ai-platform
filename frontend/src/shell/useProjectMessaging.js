import { useCallback } from "react";
import { detectIntent } from "../app/utils";
import { sendKolibriRequest } from "../runtime/kolibriApi";
import {
  buildTaskForIntent,
  mergeArtifacts,
  projectMessage,
  projectTitle,
  taskCanvas,
  upsertCanvas,
} from "./projectModel";

export function useProjectMessaging({
  busyProjects,
  dispatch,
  projects,
  setProjectBusy,
  updateProject,
}) {
  return useCallback(async (projectId, text, selectedTool = "", executionMode = "fast") => {
    if (!text.trim() || busyProjects[projectId]) return;
    const project = projects.find((item) => item.id === projectId);
    if (!project) return;

    const intent = detectIntent(text, selectedTool || project.draftTool);
    const title = projectTitle(project, text);
    const userMessage = projectMessage("user", text);

    const reply = projectMessage("assistant", "", "running");
    updateProject(projectId, (current) => ({
      ...current,
      title,
      draftTool: "",
      messages: [...current.messages, userMessage, reply],
    }));
    dispatch({ type: "UPDATE", id: `workspace:${projectId}`, window: { title } });
    setProjectBusy(projectId, true);

    const task = buildTaskForIntent(intent, text);
    try {
      const response = await sendKolibriRequest({
        text,
        messages: project.messages,
        task,
        workstreamId: projectId,
        executionMode,
        onWorkSummary: (workSummary) => updateProject(projectId, (current) => ({
          ...current,
          messages: current.messages.map((message) => message.id === reply.id
            ? { ...message, workSummary }
            : message),
        })),
      });
      const taskStatus = response.task?.status || "completed";
      const answer = response.text || (taskStatus === "incomplete"
        ? "Результат создан частично; недостающие файлы отмечены отдельно."
        : "Готово.");
      const canvas = task ? taskCanvas({
        id: reply.id,
        intent,
        title: text.slice(0, 84),
        status: taskStatus,
        text: response.text,
        task: response.task,
        artifacts: response.artifacts,
        endpoint: response.endpoint,
        workSummary: response.workSummary,
      }) : null;
      updateProject(projectId, (current) => ({
        ...current,
        messages: current.messages.map((message) => message.id === reply.id
          ? { ...message, text: answer, status: taskStatus, workSummary: response.workSummary, ...(canvas ? { canvasId: canvas.id } : {}) }
          : message),
        artifacts: mergeArtifacts(current.artifacts, response.artifacts),
        canvases: canvas ? upsertCanvas(current.canvases, canvas) : current.canvases,
        ...(canvas ? { viewMode: "editor" } : {}),
      }));
    } catch (error) {
      updateProject(projectId, (current) => ({
        ...current,
        messages: current.messages.map((message) => message.id === reply.id
          ? { ...message, text: error?.message || "Исполнительный контур временно недоступен", status: "failed" }
          : message),
      }));
    } finally {
      setProjectBusy(projectId, false);
    }
  }, [busyProjects, dispatch, projects, setProjectBusy, updateProject]);
}
