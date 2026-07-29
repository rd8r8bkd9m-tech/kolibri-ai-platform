import type { ReactNode } from "react";
import {
  EstimateDocumentCard,
  WeatherWidget as WeatherProductWidget,
} from "@/components/assistant-ui/product-widgets";
import {
  JSONGenerativeUI,
  buildPresentParameters,
  generativeUIToJSX,
  renderGenerativeUI,
  type GenerativeUILibrary,
  type GenerativeUIStatus,
  type PresentTool,
} from "@assistant-ui/react-generative-ui";

import {
  kolibriGenerativeUIComponentSchemas,
} from "./schema";
import {
  sanitizeKolibriGenerativeUI,
  type SanitizedGenerativeUINode,
} from "./sanitize";

export const KOLIBRI_GENERATIVE_UI_ERROR_MESSAGE =
  "Не удалось показать этот блок. Формат интерфейса не поддерживается.";

export const KOLIBRI_GENERATIVE_UI_STREAMING_MESSAGE =
  "Формирую представление…";

const CARD_TONE_CLASS = {
  neutral: "bg-card",
  subtle: "bg-muted/45",
  positive: "border-emerald-600/25 bg-emerald-500/[0.045]",
  warning: "border-amber-600/25 bg-amber-500/[0.055]",
} as const;

const GAP_CLASS = {
  compact: "gap-2",
  regular: "gap-3",
  relaxed: "gap-5",
} as const;

const ALIGN_CLASS = {
  start: "items-start",
  center: "items-center",
  stretch: "items-stretch",
} as const;

const GRID_CLASS = {
  1: "grid-cols-1",
  2: "grid-cols-1 sm:grid-cols-2",
  3: "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3",
} as const;

const TEXT_TONE_CLASS = {
  default: "text-foreground",
  muted: "text-muted-foreground",
  positive: "text-emerald-700 dark:text-emerald-300",
  warning: "text-amber-700 dark:text-amber-300",
} as const;

const TEXT_SIZE_CLASS = {
  small: "text-xs leading-5",
  regular: "text-sm leading-6",
  large: "text-base leading-7",
} as const;

const BADGE_TONE_CLASS = {
  neutral: "border-border bg-muted/55 text-muted-foreground",
  positive:
    "border-emerald-600/20 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  warning:
    "border-amber-600/20 bg-amber-500/10 text-amber-700 dark:text-amber-300",
  critical:
    "border-destructive/20 bg-destructive/10 text-destructive",
} as const;

function safeClassName<T extends Record<string | number, string>>(
  values: T,
  requested: unknown,
  fallback: keyof T,
): string {
  if (
    (typeof requested === "string" || typeof requested === "number") &&
    Object.hasOwn(values, requested)
  ) {
    return values[requested as keyof T];
  }
  return values[fallback];
}

function QuietGenerativeUIFallback({
  streaming = false,
}: {
  streaming?: boolean;
}) {
  return (
    <div
      className="rounded-lg border border-dashed border-border bg-muted/25 px-3 py-2 text-sm text-muted-foreground"
      role="status"
      aria-live="polite"
    >
      {streaming
        ? KOLIBRI_GENERATIVE_UI_STREAMING_MESSAGE
        : KOLIBRI_GENERATIVE_UI_ERROR_MESSAGE}
    </div>
  );
}

function Heading({
  heading,
  level = 3,
}: {
  heading: string;
  level?: 2 | 3 | 4;
}) {
  const className =
    level === 2
      ? "text-lg font-semibold tracking-tight"
      : level === 3
        ? "text-base font-semibold"
        : "text-sm font-semibold";

  if (level === 2) return <h2 className={className}>{heading}</h2>;
  if (level === 4) return <h4 className={className}>{heading}</h4>;
  return <h3 className={className}>{heading}</h3>;
}

export const kolibriGenerativeUILibrary = {
  Card: {
    description:
      "Спокойная карточка Kolibri для одной связной группы данных. Может содержать дочерние компоненты.",
    properties: kolibriGenerativeUIComponentSchemas.Card,
    render: ({
      title,
      description,
      cardTone = "neutral",
      children,
    }) => (
      <section
        className={`rounded-xl border border-border px-4 py-3 ${safeClassName(CARD_TONE_CLASS, cardTone, "neutral")}`}
      >
        {title ? <h3 className="text-sm font-semibold">{title}</h3> : null}
        {description ? (
          <p className="mt-1 text-sm leading-6 text-muted-foreground">
            {description}
          </p>
        ) : null}
        {children ? (
          <div className={title || description ? "mt-3" : undefined}>
            {children}
          </div>
        ) : null}
      </section>
    ),
  },
  Stack: {
    description:
      "Вертикальная группа дочерних компонентов с контролируемым интервалом.",
    properties: kolibriGenerativeUIComponentSchemas.Stack,
    render: ({ gap = "regular", align = "stretch", children }) => (
      <div
        className={`flex min-w-0 flex-col ${safeClassName(GAP_CLASS, gap, "regular")} ${safeClassName(ALIGN_CLASS, align, "stretch")}`}
      >
        {children}
      </div>
    ),
  },
  Grid: {
    description:
      "Адаптивная сетка из одного, двух или трёх столбцов для сравнимых блоков.",
    properties: kolibriGenerativeUIComponentSchemas.Grid,
    render: ({ columns = 2, gridGap = "regular", children }) => (
      <div
        className={`grid min-w-0 ${safeClassName(GRID_CLASS, columns, 2)} ${safeClassName(GAP_CLASS, gridGap, "regular")}`}
      >
        {children}
      </div>
    ),
  },
  Heading: {
    description: "Короткий заголовок раздела второго, третьего или четвёртого уровня.",
    properties: kolibriGenerativeUIComponentSchemas.Heading,
    render: ({ heading, level }) => (
      <Heading heading={heading} level={level} />
    ),
  },
  Text: {
    description:
      "Небольшой текстовый блок. Для длинных документов следует использовать Canvas.",
    properties: kolibriGenerativeUIComponentSchemas.Text,
    render: ({
      text,
      textTone = "default",
      textSize = "regular",
    }) => (
      <p
        className={`whitespace-pre-wrap ${safeClassName(TEXT_TONE_CLASS, textTone, "default")} ${safeClassName(TEXT_SIZE_CLASS, textSize, "regular")}`}
      >
        {text}
      </p>
    ),
  },
  Badge: {
    description: "Короткая неинтерактивная метка статуса или категории.",
    properties: kolibriGenerativeUIComponentSchemas.Badge,
    render: ({ label, badgeTone = "neutral" }) => (
      <span
        className={`inline-flex w-fit items-center rounded-full border px-2 py-0.5 text-xs font-medium ${safeClassName(BADGE_TONE_CLASS, badgeTone, "neutral")}`}
      >
        {label}
      </span>
    ),
  },
  Metric: {
    description:
      "Одна проверяемая метрика: подпись, значение и необязательное пояснение.",
    properties: kolibriGenerativeUIComponentSchemas.Metric,
    render: ({ metricLabel, metricValue, metricNote }) => (
      <div className="min-w-0">
        <div className="text-xs text-muted-foreground">{metricLabel}</div>
        <div className="mt-0.5 break-words text-xl font-semibold tabular-nums">
          {metricValue}
        </div>
        {metricNote ? (
          <div className="mt-1 text-xs leading-5 text-muted-foreground">
            {metricNote}
          </div>
        ) : null}
      </div>
    ),
  },
  KeyValue: {
    description: "Одна строка «ключ — значение» для компактных реквизитов.",
    properties: kolibriGenerativeUIComponentSchemas.KeyValue,
    render: ({ keyLabel, keyValue }) => (
      <dl className="grid min-w-0 grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)] gap-3 border-b border-border/70 py-2 last:border-b-0">
        <dt className="text-sm text-muted-foreground">{keyLabel}</dt>
        <dd className="break-words text-right text-sm font-medium tabular-nums">
          {keyValue}
        </dd>
      </dl>
    ),
  },
  Progress: {
    description:
      "Только индикатор уже известного прогресса от 0 до 100, без управления.",
    properties: kolibriGenerativeUIComponentSchemas.Progress,
    render: ({ progressLabel, value, valueLabel }) => (
      <div className="min-w-0">
        {progressLabel || valueLabel ? (
          <div className="mb-1.5 flex items-baseline justify-between gap-3 text-xs">
            <span className="text-muted-foreground">{progressLabel}</span>
            <span className="font-medium tabular-nums">
              {valueLabel ?? `${value}%`}
            </span>
          </div>
        ) : null}
        <progress
          className="h-1.5 w-full overflow-hidden rounded-full"
          value={value}
          max={100}
          aria-label={progressLabel ?? "Прогресс"}
        />
      </div>
    ),
  },
  WeatherWidget: {
    description:
      "Погодный ответ выбранной модели: город, доступные показатели, прогноз и реальные источники модели.",
    properties: kolibriGenerativeUIComponentSchemas.WeatherWidget,
    render: (props) => <WeatherProductWidget {...props} />,
  },
  EstimateEditor: {
    description:
      "Сохранённая смета проекта: компактная карточка раскрывает встроенный редактор с автосохранением.",
    properties: kolibriGenerativeUIComponentSchemas.EstimateEditor,
    render: (props) => <EstimateDocumentCard {...props} />,
  },
  Divider: {
    description: "Тонкий неинтерактивный разделитель между смысловыми блоками.",
    properties: kolibriGenerativeUIComponentSchemas.Divider,
    render: () => <hr className="border-border/80" />,
  },
} satisfies GenerativeUILibrary;

export const kolibriPresentParameters = buildPresentParameters(
  kolibriGenerativeUILibrary,
);

export const kolibriJSONGenerativeUI = new JSONGenerativeUI({
  library: kolibriGenerativeUILibrary,
});

function statusFromToolCall(status: { type: string }): GenerativeUIStatus {
  return status.type === "running" ? "streaming" : "done";
}

export function renderValidatedKolibriGenerativeUI(
  input: unknown,
  status: GenerativeUIStatus = "done",
): ReactNode {
  const result = sanitizeKolibriGenerativeUI(input);
  if (!result.ok) {
    return <QuietGenerativeUIFallback streaming={status === "streaming"} />;
  }
  return renderGenerativeUI(result.value, kolibriGenerativeUILibrary, {
    status,
  });
}

const officialPresentTool = kolibriJSONGenerativeUI.present();

export const kolibriPresentTool = {
  ...officialPresentTool,
  parameters: kolibriPresentParameters,
  render: ({
    args,
    status,
  }: {
    args: unknown;
    status: { type: string };
  }) =>
    renderValidatedKolibriGenerativeUI(inputFromToolArgs(args), statusFromToolCall(status)),
} as PresentTool;

function inputFromToolArgs(args: unknown): unknown {
  return args;
}

export function serializeKolibriGenerativeUI(input: unknown): string {
  const result = sanitizeKolibriGenerativeUI(input);
  if (!result.ok) return "";
  return generativeUIToJSX(result.value, {
    escape: true,
    pretty: true,
  });
}

export function isValidKolibriGenerativeUI(
  input: unknown,
): input is SanitizedGenerativeUINode {
  return sanitizeKolibriGenerativeUI(input).ok;
}
