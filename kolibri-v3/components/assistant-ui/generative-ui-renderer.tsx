"use client";

import {
  KOLIBRI_GENERATIVE_UI_ERROR_MESSAGE,
  KOLIBRI_GENERATIVE_UI_STREAMING_MESSAGE,
  kolibriGenerativeUILibrary,
  sanitizeKolibriGenerativeUI,
  serializeKolibriGenerativeUI,
} from "@/lib/generative-ui";
import { renderGenerativeUI } from "@assistant-ui/react-generative-ui";

export type KolibriGenerativeUIRendererProps = {
  spec: unknown;
  status?: "streaming" | "done";
  inspectSource?: boolean;
};

export type KolibriGenerativeUIProps = {
  node: unknown;
  status?: "streaming" | "done";
  inspectable?: boolean;
};

export function KolibriGenerativeUI({
  node,
  status = "done",
  inspectable = false,
}: KolibriGenerativeUIProps) {
  return (
    <KolibriGenerativeUIRenderer
      spec={node}
      status={status}
      inspectSource={inspectable}
    />
  );
}

export function KolibriGenerativeUIRenderer({
  spec,
  status = "done",
  inspectSource = false,
}: KolibriGenerativeUIRendererProps) {
  const validation = sanitizeKolibriGenerativeUI(spec);

  if (!validation.ok) {
    return (
      <div
        className="rounded-lg border border-dashed border-border bg-muted/25 px-3 py-2 text-sm text-muted-foreground"
        role="status"
        aria-live="polite"
        data-slot="kolibri-generative-ui-fallback"
      >
        {status === "streaming"
          ? KOLIBRI_GENERATIVE_UI_STREAMING_MESSAGE
          : KOLIBRI_GENERATIVE_UI_ERROR_MESSAGE}
      </div>
    );
  }

  const source = inspectSource
    ? serializeKolibriGenerativeUI(validation.value)
    : "";
  const rootType =
    typeof validation.value === "object" &&
    validation.value !== null &&
    !Array.isArray(validation.value) &&
    "$type" in validation.value &&
    typeof validation.value.$type === "string"
      ? validation.value.$type
      : null;
  const isProductWidget =
    rootType === "WeatherWidget" || rootType === "EstimateEditor";

  if (isProductWidget) {
    return (
      <div
        className="min-w-0"
        data-slot="kolibri-product-widget"
        data-generative-ui-status={status}
      >
        {renderGenerativeUI(validation.value, kolibriGenerativeUILibrary, {
          status,
        })}
      </div>
    );
  }

  return (
    <div
      className="min-w-0 rounded-xl border border-border/70 bg-card p-3"
      data-slot="kolibri-generative-ui"
      data-generative-ui-status={status}
      aria-label="Сгенерированное представление Kolibri"
    >
      <p
        className="mb-2 text-[10px] font-medium tracking-wide text-muted-foreground"
        data-slot="kolibri-generative-ui-provenance"
      >
        Представление ИИ · не является подтверждением
      </p>
      {renderGenerativeUI(validation.value, kolibriGenerativeUILibrary, {
        status,
      })}

      {inspectSource ? (
        <details className="mt-2 text-xs text-muted-foreground">
          <summary className="w-fit select-none rounded px-1 py-0.5 hover:bg-muted">
            Структура блока
          </summary>
          <pre
            className="mt-1 max-h-56 overflow-auto rounded-lg border border-border bg-muted/35 p-3 text-[11px] leading-5"
            aria-label="Безопасное описание сгенерированного интерфейса"
            tabIndex={0}
          >
            <code>{source}</code>
          </pre>
        </details>
      ) : null}
    </div>
  );
}
