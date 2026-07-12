import { initialWorkbench } from "../workbench/reducer";
import {
  HISTORY_STORAGE_KEY,
  INTENT_WORDS,
  PROJECTS_STORAGE_KEY,
  WORKSPACE_STORAGE_KEY,
} from "./constants";
import { recoverInterruptedProjects } from "../shell/projectMessageRecovery.js";

export function makeId(prefix) {
  const fallback = `${Date.now()}_${Math.random().toString(16).slice(2)}`;
  return `${prefix}_${globalThis.crypto?.randomUUID?.() || fallback}`;
}

export function detectIntent(text, selectedTool) {
  if (selectedTool) return selectedTool;
  const normalized = String(text || "").toLowerCase();
  const asksForArtifact = /(сдел|созда|состав|подготов|рассч|разработ|сгенер|дай|хочу\s+получ|нуж(?:ен|на|но|ны))/.test(normalized);
  if (!asksForArtifact) return "response";
  return Object.entries(INTENT_WORDS)
    .find(([, words]) => words.some((word) => normalized.includes(word)))?.[0] || "response";
}

export function readHistory() {
  try {
    const value = JSON.parse(globalThis.localStorage.getItem(HISTORY_STORAGE_KEY) || "[]");
    return Array.isArray(value) ? value : [];
  } catch {
    return [];
  }
}

export function createProject(title = "Новый проект") {
  const now = new Date().toISOString();
  return {
    id: makeId("project"),
    title,
    messages: [],
    artifacts: [],
    canvases: [],
    viewMode: "dialog",
    executionMode: "fast",
    createdAt: now,
    updatedAt: now,
  };
}

export function readProjects() {
  try {
    const raw = globalThis.localStorage?.getItem(PROJECTS_STORAGE_KEY);
    const stored = JSON.parse(raw || "null");
    if (Array.isArray(stored)) return stored.length ? recoverInterruptedProjects(stored) : [createProject()];
  } catch {
    // Continue with the v1 history migration below.
  }
  const history = readHistory();
  if (!history.length) return [createProject()];
  return recoverInterruptedProjects(history.map((item) => ({
    id: item.projectId || makeId("project"),
    title: item.title || "Сохранённый проект",
    messages: item.text ? [{ id: makeId("message"), role: "assistant", text: item.text, createdAt: item.createdAt }] : [],
    artifacts: item.task?.artifacts || item.artifacts || [],
    canvases: [],
    viewMode: "dialog",
    executionMode: "fast",
    createdAt: item.createdAt || new Date().toISOString(),
    updatedAt: item.createdAt || new Date().toISOString(),
  })));
}

export function readWorkspace() {
  try {
    const value = JSON.parse(globalThis.localStorage.getItem(WORKSPACE_STORAGE_KEY) || "null");
    if (!value || !Array.isArray(value.windows)) return initialWorkbench;
    return {
      ...initialWorkbench,
      ...value,
      windows: value.windows.map((item) => item?.payload?.status === "running"
        ? {
            ...item,
            payload: {
              ...item.payload,
              status: "incomplete",
              statusLabel: "Можно продолжить",
              error: "Выполнение было прервано. Запустите задачу снова.",
            },
          }
        : item),
    };
  } catch {
    return initialWorkbench;
  }
}
