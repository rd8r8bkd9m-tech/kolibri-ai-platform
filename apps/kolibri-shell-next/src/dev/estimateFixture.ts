import type {
  EstimateArtifact,
  SafeWorkTrace,
  ShellSnapshot,
  TraceStage,
} from "@domain/shell";
import type { ShellClient } from "@services/shellClient";

export const VISUAL_FIXTURE_SENTINEL = "KOLIBRI_VISUAL_FIXTURE_V1_DEV_ONLY";

const estimate: EstimateArtifact = {
  id: "estimate-100m2",
  title: "Предварительная смета · дом 100 м²",
  location: "Лениногорск",
  pricedAt: "12.07.2026",
  sourceSummary: "актуальные прайс-листы поставщиков и открытые сметные базы города Лениногорск.",
  fileName: "Смета_дом_100м2_Лениногорск_12.07.2026.pdf",
  fileSizeLabel: "PDF · 124 КБ",
  lines: [
    {
      id: "foundation",
      kind: "foundation",
      label: "Фундамент (ленточный ж/б)",
      unit: "м³",
      quantity: 24,
      unitPrice: 9_500,
    },
    {
      id: "walls",
      kind: "shell",
      label: "Стены (газобетон 400 мм с кладкой)",
      unit: "м²",
      quantity: 240,
      unitPrice: 2_755,
    },
    {
      id: "roof",
      kind: "roof",
      label: "Кровля (металлочерепица с работой)",
      unit: "м²",
      quantity: 120,
      unitPrice: 2_750,
    },
    {
      id: "openings",
      kind: "openings",
      label: "Окна и двери (ПВХ)",
      unit: "м²",
      quantity: 24,
      unitPrice: 12_500,
    },
    {
      id: "systems",
      kind: "systems",
      label: "Инженерные сети (электрика, вода, канализация)",
      unit: "компл.",
      quantity: 1,
      unitPrice: 481_000,
    },
  ],
};

const desktopStages: TraceStage[] = [
  { id: "understood", label: "Понял задачу", state: "done" },
  { id: "gathered", label: "Собрал данные", state: "done" },
  { id: "estimated", label: "Сформировал смету", state: "done" },
  { id: "verified", label: "Проверил цены", state: "done" },
  { id: "prepared", label: "Подготовил результат", state: "done" },
];

const mobileStages: TraceStage[] = [
  { id: "understood", label: "Понял задачу", state: "done" },
  { id: "gathered", label: "Собрал данные", state: "done" },
  { id: "estimated", label: "Сформировал смету", state: "done" },
  { id: "verified", label: "Проверяю цены", state: "active" },
];

function fixtureTrace(compact: boolean): SafeWorkTrace {
  return {
    id: "trace-estimate",
    status: compact ? "running" : "completed",
    stages: compact ? mobileStages : desktopStages,
    agents: compact
      ? [
          {
            id: "estimator",
            label: "Сметчик",
            stateLabel: "считает",
            tone: "teal",
            icon: "calculator",
          },
          {
            id: "verifier",
            label: "Проверяющий",
            stateLabel: "ожидает",
            tone: "yellow",
            icon: "shield",
          },
        ]
      : [],
  };
}

function fixtureSnapshot(compact: boolean): ShellSnapshot {
  return {
    project: { id: "project-home-100", title: "Дом 100 м²", location: "Лениногорск" },
    messages: compact
      ? [
          {
            id: "user-fixture",
            author: "user",
            content: "гамбургер динамично меняется на птичку\nи наоборот как в gpt",
            sentAt: "11:24",
            delivery: "sent",
          },
          {
            id: "assistant-fixture",
            author: "assistant",
            content: "Понял задачу. Реализую динамическую смену иконки между гамбургером и птицей, как в GPT.",
            sentAt: "11:24",
            delivery: "sent",
          },
        ]
      : [
          {
            id: "user-fixture",
            author: "user",
            content: "Сделай предварительную смету на строительство дома 100 м² в Лениногорске.",
            sentAt: "11:42",
            delivery: "sent",
          },
          {
            id: "assistant-fixture",
            author: "assistant",
            content: "Готово. Подготовил предварительную смету на дом 100 м² в Лениногорске.\nНиже — ключевые разделы и итоговая стоимость.",
            sentAt: "11:42",
            delivery: "sent",
          },
        ],
    trace: fixtureTrace(compact),
    estimate,
    activeResponseId: compact ? "response-fixture-running" : null,
  };
}

const wait = (milliseconds: number, signal: AbortSignal) =>
  new Promise<void>((resolve, reject) => {
    const timeout = window.setTimeout(resolve, milliseconds);
    signal.addEventListener(
      "abort",
      () => {
        window.clearTimeout(timeout);
        reject(new DOMException("Aborted", "AbortError"));
      },
      { once: true },
    );
  });

function runningTrace(done: number): SafeWorkTrace {
  const labels = ["Понял задачу", "Собрал данные", "Сформировал ответ", "Проверил результат"];
  return {
    id: "trace-live-fixture",
    status: done === labels.length ? "completed" : "running",
    stages: labels.map((label, index) => ({
      id: `safe-${index}`,
      label,
      state: index < done ? "done" : index === done ? "active" : "queued",
    })),
    agents: [],
  };
}

export function createEstimateFixtureClient(compact: boolean): ShellClient {
  void VISUAL_FIXTURE_SENTINEL;
  return {
    async start(emit) {
      emit({ type: "snapshot", snapshot: fixtureSnapshot(compact) });
      return () => undefined;
    },
    async send(input, emit, signal) {
      emit({ type: "message.delivery", id: input.clientMessageId, delivery: "sent" });
      for (let completed = 0; completed <= 4; completed += 1) {
        emit({ type: "trace.updated", trace: runningTrace(completed) });
        if (completed < 4) await wait(180, signal);
      }
      emit({
        type: "message.added",
        message: {
          id: `fixture-reply-${input.clientMessageId}`,
          author: "assistant",
          content: "Готово. Я обновил результат и оставил в ходе работы только безопасные этапы.",
          sentAt: new Date().toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" }),
          delivery: "sent",
        },
      });
    },
  };
}
