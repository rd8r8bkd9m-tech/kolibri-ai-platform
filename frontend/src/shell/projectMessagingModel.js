import { detectIntent } from "../app/utils";
import { mergeArtifacts, projectMessage, projectTitle, upsertCanvas } from "./projectModel";

function requestHistoryForRetry(project, replyId, prompt) {
  const replyIndex = project.messages.findIndex((message) => message.id === replyId);
  if (replyIndex < 0) return project.messages;
  const history = project.messages.slice(0, replyIndex);
  const preceding = history.at(-1);
  if (preceding?.role === "user" && String(preceding.text || "").trim() === prompt) history.pop();
  return history;
}

export function prepareProjectTurn(project, text, selectedTool, executionMode, options = {}) {
  const prompt = String(text || "").trim();
  if (!prompt) return null;
  const retryMessage = options.retryMessageId
    ? project.messages.find((message) => message.id === options.retryMessageId && message.recoverable)
    : null;
  const retrying = Boolean(retryMessage && retryMessage.retryPrompt === prompt);
  const selected = selectedTool || retryMessage?.retryTool || project.draftTool || "";
  const startedAt = new Date().toISOString();
  const reply = retrying
    ? {
        ...retryMessage,
        text: "",
        progressText: "",
        status: "running",
        recoverable: false,
        excludeFromContext: false,
        retryPrompt: prompt,
        retryTool: selected,
        retryExecutionMode: executionMode,
        workSummary: null,
        startedAt,
        updatedAt: startedAt,
      }
    : projectMessage("assistant", "", "running", {
        recoverable: false,
        excludeFromContext: false,
        retryPrompt: prompt,
        retryTool: selected,
        retryExecutionMode: executionMode,
        startedAt,
      });
  return {
    prompt,
    intent: detectIntent(prompt, selected),
    title: projectTitle(project, prompt),
    reply,
    retrying,
    selectedTool: selected,
    userMessage: retrying ? null : projectMessage("user", prompt),
    requestMessages: retrying ? requestHistoryForRetry(project, reply.id, prompt) : project.messages,
  };
}

export function beginTurnProject(current, turn) {
  return {
    ...current,
    title: turn.title,
    draftTool: "",
    messages: turn.retrying
      ? current.messages.map((message) => message.id === turn.reply.id ? turn.reply : message)
      : [...current.messages, turn.userMessage, turn.reply],
  };
}

export function patchTurnMessage(current, replyId, patch) {
  return {
    ...current,
    messages: current.messages.map((message) => message.id === replyId
      ? { ...message, ...patch }
      : message),
  };
}

export function workProgressText(workSummary, progress = {}) {
  if (typeof progress.detail === "string" && progress.detail.trim()) return progress.detail.trim();
  const items = Array.isArray(workSummary?.items) ? workSummary.items : [];
  const active = items.find((item) => item.kind === progress.activeKind)
    || items.find((item) => item.status === "running")
    || items.find((item) => item.status === "pending")
    || items.at(-1);
  return active?.detail || "";
}

export function completedAssistantReply(reply, response, canvas) {
  return {
    ...reply,
    text: String(response.text || "").trim(),
    progressText: "",
    status: response.task?.status || "completed",
    recoverable: false,
    excludeFromContext: false,
    workSummary: response.workSummary,
    responseId: response.taskId,
    updatedAt: new Date().toISOString(),
    ...(canvas ? { canvasId: canvas.id } : {}),
  };
}

export function completeTurnProject(current, completedReply, response, canvas) {
  const currentSummary = current.messages.find((message) => message.id === completedReply.id)?.workSummary;
  const project = patchTurnMessage(current, completedReply.id, {
    ...completedReply,
    workSummary: response.workSummary || currentSummary,
  });
  return {
    ...project,
    artifacts: mergeArtifacts(current.artifacts, canvas?.artifacts || response.artifacts),
    canvases: canvas ? upsertCanvas(current.canvases, canvas) : current.canvases,
    ...(canvas ? { viewMode: "editor" } : {}),
  };
}

export function failedAssistantReply(reply, turn, error, text) {
  const status = Number(error?.status) || 0;
  const recoverable = error?.name === "AbortError"
    || status === 0 || status === 401 || status === 408 || status === 409 || status === 429 || status >= 500;
  return {
    ...reply,
    text,
    progressText: "",
    status: error?.name === "AbortError" ? "cancelled" : "failed",
    recoverable,
    excludeFromContext: true,
    retryPrompt: turn.prompt,
    retryTool: turn.selectedTool,
    retryExecutionMode: reply.retryExecutionMode,
    updatedAt: new Date().toISOString(),
  };
}
