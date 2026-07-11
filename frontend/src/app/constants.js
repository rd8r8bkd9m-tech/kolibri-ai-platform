import {
  Calculator,
  Code2,
  FileText,
  Files,
  Globe2,
  History,
} from "lucide-react";

export const TOOLS = Object.freeze([
  { id: "estimate", label: "Смета", icon: Calculator, hint: "Точный расчёт" },
  { id: "document", label: "Документ", icon: FileText, hint: "DOCX или PDF" },
  { id: "site", label: "Сайт", icon: Globe2, hint: "Код и preview" },
  { id: "app", label: "Приложение", icon: Code2, hint: "Сборка и тесты" },
]);

export const SYSTEM_APPS = Object.freeze([
  { id: "projects", label: "История", icon: History },
  { id: "files", label: "Файлы", icon: Files },
]);

export const EXECUTION_MODES = Object.freeze([
  { id: "fast", label: "Быстро", hint: "Диалог и короткие задачи" },
  { id: "codex", label: "Codex", hint: "Разработка через фабрику" },
]);

export const INTENT_WORDS = Object.freeze({
  estimate: ["смет", "расчет", "расчёт", "стоимост"],
  document: ["документ", "договор", "коммерческ", "отчет", "отчёт", "акт"],
  site: ["сайт", "лендинг", "web-сайт", "веб-сайт"],
  app: ["приложен", "сервис", "программ"],
});

export const HISTORY_STORAGE_KEY = "kolibri.vista.history.v1";
export const PROJECTS_STORAGE_KEY = "kolibri.vista.projects.v2";
export const ACTIVE_PROJECT_STORAGE_KEY = "kolibri.vista.active-project.v1";
export const WORKSPACE_STORAGE_KEY = "kolibri.vista.workspace.v2";
