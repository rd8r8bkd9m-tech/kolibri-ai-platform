import { useCallback } from "react";
import { publicErrorMessage, sendKolibriRequest } from "../runtime/kolibriApi";
import {
  beginTurnProject,
  completeTurnProject,
  completedAssistantReply,
  failedAssistantReply,
  patchTurnMessage,
  prepareProjectTurn,
  workProgressText,
} from "./projectMessagingModel";
import { buildTaskForIntent, taskCanvas } from "./projectModel";

export function useProjectMessaging({ beginProjectRequest, busyProjects, dispatch, endProjectRequest, ensureProjectRemote, reconcileProjectRemote, projects, syncProjectMessage, updateProject }) {
  return useCallback(async (projectId, text, selectedTool = "", executionMode = "fast", options = {}) => {
    if (busyProjects[projectId]) return;
    const project = projects.find((item) => item.id === projectId);
    if (!project) return;
    const turn = prepareProjectTurn(project, text, selectedTool, executionMode, options);
    if (!turn) return;

    updateProject(projectId, (current) => beginTurnProject(current, turn));
    dispatch({ type: "UPDATE", id: `workspace:${projectId}`, window: { title: turn.title } });
    const request = beginProjectRequest(projectId);
    const task = buildTaskForIntent(turn.intent, turn.prompt);

    try {
      let remoteProjectId = await ensureProjectRemote(projectId, request.signal);
      if (turn.userMessage) {
        await syncProjectMessage(projectId, turn.userMessage, { signal: request.signal }).catch(() => null);
        remoteProjectId = await ensureProjectRemote(projectId, request.signal);
      }
      const response = await sendKolibriRequest({
        text: turn.prompt,
        messages: turn.requestMessages,
        task,
        projectId: remoteProjectId,
        reconcileProjectId: ({ failedProjectId }) => reconcileProjectRemote(projectId, failedProjectId, request.signal),
        workstreamId: projectId,
        executionMode,
        signal: request.signal,
        ...(task ? {} : {
          onTextDelta: (_delta, accumulatedText) => updateProject(
            projectId,
            (current) => patchTurnMessage(current, turn.reply.id, { text: accumulatedText, progressText: "" }),
          ),
        }),
        onWorkSummary: (workSummary, progress) => updateProject(
          projectId,
          (current) => patchTurnMessage(current, turn.reply.id, {
            workSummary,
            progressText: workProgressText(workSummary, progress),
          }),
        ),
      });
      const answer = String(response.text || "").trim();
      if (!answer) throw new Error("Проверенный текст ответа не получен.");
      const canvas = task ? taskCanvas({
        id: turn.reply.id,
        intent: turn.intent,
        title: turn.prompt.slice(0, 84),
        status: response.task?.status || "completed",
        text: response.text,
        task: response.task,
        artifacts: response.artifacts,
        endpoint: response.endpoint,
        workSummary: response.workSummary,
      }) : null;
      const completedReply = completedAssistantReply(turn.reply, response, canvas);
      updateProject(projectId, (current) => completeTurnProject(current, completedReply, response, canvas));
      await syncProjectMessage(projectId, completedReply, {
        responseId: response.taskId,
        signal: request.signal,
      }).catch(() => null);
    } catch (error) {
      const failedReply = failedAssistantReply(turn.reply, turn, error, publicErrorMessage(error));
      updateProject(projectId, (current) => patchTurnMessage(current, turn.reply.id, failedReply));
      if (!request.signal.aborted) {
        await syncProjectMessage(projectId, failedReply, { signal: request.signal }).catch(() => {});
      }
    } finally {
      endProjectRequest(projectId, request.token);
    }
  }, [beginProjectRequest, busyProjects, dispatch, endProjectRequest, ensureProjectRemote, projects, reconcileProjectRemote, syncProjectMessage, updateProject]);
}
