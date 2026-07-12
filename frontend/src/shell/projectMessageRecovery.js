const ACTIVE_MESSAGE_STATUSES = new Set(["pending", "running"]);
const FAILED_MESSAGE_STATUSES = new Set(["failed"]);

export const INTERRUPTED_RESPONSE_TEXT = "Ответ прерван до завершения. История проекта сохранена — запрос можно повторить.";
export const FAILED_RESPONSE_TEXT = "Ответ не был завершён. Контекст проекта сохранён — запрос можно повторить.";

function cleanText(value) {
  return typeof value === "string" ? value.trim() : "";
}

function interruptedWorkSummary(summary) {
  if (!summary || !Array.isArray(summary.items)) return summary;
  return {
    ...summary,
    items: summary.items.map((item) => ACTIVE_MESSAGE_STATUSES.has(item?.status)
      ? { ...item, status: "incomplete" }
      : item),
  };
}

export function isRecoverableAssistantMessage(message) {
  return Boolean(
    message?.role === "assistant"
    && message.recoverable === true
    && cleanText(message.retryPrompt),
  );
}

/**
 * A browser reload aborts the page-owned fetch, even though the project itself
 * remains durable. Never hydrate or persist a blank assistant article for that
 * interrupted turn. The preceding user prompt becomes an explicit, safe retry
 * binding; partial provider text is deliberately not presented as verified.
 */
export function recoverInterruptedProject(project) {
  if (!project || !Array.isArray(project.messages)) return project;
  let previousUserPrompt = "";
  const messages = project.messages.map((message) => {
    if (message?.role === "user") {
      previousUserPrompt = cleanText(message.text);
      return message;
    }
    const blankAssistant = message?.role === "assistant"
      && !cleanText(message.text)
      && !cleanText(message.progressText);
    const markedRecoverable = message?.recoverable === true || message?.excludeFromContext === true;
    const failedAssistant = message?.role === "assistant" && FAILED_MESSAGE_STATUSES.has(message.status);
    if (message?.role !== "assistant" || (!ACTIVE_MESSAGE_STATUSES.has(message.status) && !blankAssistant && !markedRecoverable && !failedAssistant)) return message;
    const retryPrompt = cleanText(message.retryPrompt) || previousUserPrompt;
    return {
      ...message,
      // Old provider/runtime wording must not become permanent project UI.
      // The structured Work Summary keeps the actionable failure category;
      // the conversation receives one stable, retryable recovery sentence.
      text: failedAssistant
        ? FAILED_RESPONSE_TEXT
        : cleanText(message.text) || INTERRUPTED_RESPONSE_TEXT,
      progressText: "",
      status: "incomplete",
      recoverable: Boolean(retryPrompt),
      excludeFromContext: true,
      ...(retryPrompt ? { retryPrompt } : {}),
      retryTool: cleanText(message.retryTool),
      retryExecutionMode: cleanText(message.retryExecutionMode) || project.executionMode || "fast",
      workSummary: interruptedWorkSummary(message.workSummary),
      updatedAt: message.updatedAt || message.createdAt || project.updatedAt,
    };
  });
  return { ...project, messages };
}

export function recoverInterruptedProjects(projects) {
  return (Array.isArray(projects) ? projects : []).map(recoverInterruptedProject);
}
