"use client";

import {
  AuiProvider,
  Suggestions,
  useAui,
} from "@assistant-ui/react";

import { WorkspaceShell } from "@/components/kolibri-shell/workspace-shell";

const kolibriSuggestions = Suggestions([
  {
    title: "Собрать смету",
    label: "по описанию и файлам",
    prompt:
      "Собери предварительную смету проекта. Сначала отдели факты от допущений и перечисли недостающие исходные данные.",
  },
  {
    title: "Разобрать проект",
    label: "и составить план работ",
    prompt:
      "Разбери исходные данные проекта и предложи проверяемый план работ с этапами, рисками и результатами.",
  },
  {
    title: "Подготовить документы",
    label: "КП, счёт и договор",
    prompt:
      "Подготовь связанный комплект документов для проекта. Покажи, какие данные и согласования ещё нужны.",
  },
  {
    title: "Проверить расчёт",
    label: "источники и допущения",
    prompt:
      "Проверь расчёт: покажи источники, версии входных данных, допущения и позиции, требующие подтверждения.",
  },
]);

export function KolibriApp() {
  const aui = useAui({ suggestions: kolibriSuggestions });

  return (
    <AuiProvider value={aui}>
      <WorkspaceShell />
    </AuiProvider>
  );
}
