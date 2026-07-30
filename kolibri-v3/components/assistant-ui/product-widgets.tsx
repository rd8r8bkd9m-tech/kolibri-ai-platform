"use client";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { withCsrfHeader } from "@/lib/csrf";
import {
  diffEstimateDrafts,
  parseEstimateVersionConflict,
  type EstimateDraftConflictDiff,
  type EstimateDraftSnapshot,
} from "@/lib/estimate-version-conflict";
import { kolibriGenerativeUIComponentSchemas } from "@/lib/generative-ui/schema";
import { announceAuthenticationRequired } from "@/lib/identity/events";
import {
  KOLIBRI_DOCUMENTS_CHANGED_EVENT,
  announceDocumentsChanged,
  openEstimateInWorkspace,
} from "@/lib/workspace-events";
import { cn } from "@/lib/utils";
import { makeAssistantToolUI, useAuiState } from "@assistant-ui/react";
import {
  ChevronDownIcon,
  CloudIcon,
  CloudFogIcon,
  CloudLightningIcon,
  CloudRainIcon,
  CloudSnowIcon,
  CheckCircle2Icon,
  CopyIcon,
  DownloadIcon,
  DropletsIcon,
  FileSpreadsheetIcon,
  LoaderCircleIcon,
  MoreHorizontalIcon,
  MoonStarIcon,
  PlusIcon,
  RefreshCwIcon,
  SnowflakeIcon,
  SunIcon,
  Trash2Icon,
  UsersIcon,
  WindIcon,
  type LucideIcon,
} from "lucide-react";
import Image from "next/image";
import {
  Fragment,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type { z } from "zod";


type WeatherWidgetProps = z.infer<
  typeof kolibriGenerativeUIComponentSchemas.WeatherWidget
>;
type EstimateWidgetProps = z.infer<
  typeof kolibriGenerativeUIComponentSchemas.EstimateEditor
>;
type EstimateRow = EstimateWidgetProps["rows"][number];
type EditableEstimateRow = Omit<EstimateRow, "lineTotal">;
type PriceEvidence = NonNullable<EstimateRow["priceEvidence"]>;
type EnginePriceProvenance = NonNullable<
  EstimateRow["enginePriceProvenance"]
>;
type ProjectPartySummary = {
  id: string;
  role: "client" | "contractor";
  entityType: "person" | "organization";
  displayName: string;
  taxId: string | null;
  registrationCode: string | null;
};
type ProjectContextSummary = {
  projectName: string;
  objectName: string | null;
  client: ProjectPartySummary | null;
  contractor: ProjectPartySummary | null;
};
type EstimateCopyResult = {
  project: {
    id: string;
    name: string;
    objectName: string;
    threadId: string;
  };
  document: { id: string; version: number; contentHash: string };
  lineage: {
    sourceProjectId: string;
    sourceDocumentId: string;
    sourceVersion: number;
    sourceContentHash: string;
  };
};
type EstimateExportFormat = "pdf" | "xlsx" | "docx" | "csv" | "zip";
type WeatherScene =
  | "clear-day"
  | "clear-night"
  | "clouds"
  | "rain"
  | "snow"
  | "storm";

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const containsEstimateDocument = (
  content: readonly { type: string; [key: string]: unknown }[],
  documentId: string,
) =>
  content.some(
    (part) =>
      part.type === "tool-call" &&
      part.toolName === "present" &&
      isRecord(part.args) &&
      part.args.$type === "EstimateEditor" &&
      part.args.documentId === documentId,
  );

const WEATHER_ICONS: ReadonlyArray<{
  readonly codes: readonly number[];
  readonly icon: LucideIcon;
}> = [
  { codes: [0, 1], icon: SunIcon },
  { codes: [45, 48], icon: CloudFogIcon },
  { codes: [51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82], icon: CloudRainIcon },
  { codes: [71, 73, 75, 77, 85, 86], icon: CloudSnowIcon },
  { codes: [95, 96, 99], icon: CloudLightningIcon },
];

const RAIN_CODES = new Set([
  51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82,
]);
const SNOW_CODES = new Set([71, 73, 75, 77, 85, 86]);
const STORM_CODES = new Set([95, 96, 99]);
const CLOUD_CODES = new Set([2, 3, 45, 48]);

const weatherSceneFor = (
  code: number | undefined,
  condition: string,
  isDay: boolean | undefined,
): WeatherScene => {
  if (typeof code === "number") {
    if (STORM_CODES.has(code)) return "storm";
    if (SNOW_CODES.has(code)) return "snow";
    if (RAIN_CODES.has(code)) return "rain";
    if (CLOUD_CODES.has(code)) return "clouds";
    if (code === 0 || code === 1) {
      return isDay === false ? "clear-night" : "clear-day";
    }
  }

  const normalized = condition.toLocaleLowerCase("ru-RU");
  if (/(гроз|thunder)/.test(normalized)) return "storm";
  if (/(снег|snow)/.test(normalized)) return "snow";
  if (/(дожд|лив|морос|rain|shower|drizzle)/.test(normalized)) {
    return "rain";
  }
  if (/(облач|пасмур|туман|cloud|overcast|fog|mist)/.test(normalized)) {
    return "clouds";
  }
  return isDay === false ? "clear-night" : "clear-day";
};

const WEATHER_SCENE_ASSET: Record<WeatherScene, string> = {
  "clear-day": "/weather/clear-day.webp",
  "clear-night": "/weather/clear-night.webp",
  clouds: "/weather/overcast.webp",
  rain: "/weather/storm-rain.webp",
  snow: "/weather/overcast.webp",
  storm: "/weather/storm-rain.webp",
};

function WeatherSceneBackdrop({
  active,
  scene,
}: {
  active: boolean;
  scene: WeatherScene;
}) {
  const hasRain = scene === "rain" || scene === "storm";

  return (
    <div
      aria-hidden="true"
      className="kolibri-weather-scene absolute inset-0 -z-20 overflow-hidden"
      data-weather-active={active ? "true" : "false"}
      data-weather-scene={scene}
    >
      <Image
        alt=""
        className="kolibri-weather-scene__backdrop absolute inset-0 size-full object-cover"
        fill
        loading="eager"
        sizes="(max-width: 640px) 100vw, 760px"
        src={WEATHER_SCENE_ASSET[scene]}
      />

      {hasRain ? (
        <Image
          alt=""
          className="kolibri-weather-scene__rain absolute inset-0 size-full object-cover"
          fill
          sizes="(max-width: 640px) 100vw, 760px"
          src="/weather/storm-rain.webp"
        />
      ) : null}

      {scene === "clear-day" ? (
        <SunIcon className="kolibri-weather-scene__sun absolute right-[7%] top-[8%] size-24 stroke-[0.7] text-amber-100/75 sm:size-32" />
      ) : null}

      {scene === "clear-night" ? (
        <MoonStarIcon className="kolibri-weather-scene__moon absolute right-[8%] top-[9%] size-20 stroke-[0.8] text-slate-100/80 sm:size-28" />
      ) : null}

      {scene === "snow" ? (
        <>
          <SnowflakeIcon className="kolibri-weather-scene__snow kolibri-weather-scene__snow--one absolute left-[13%] top-[-12%] size-6 stroke-[1] text-white/70" />
          <SnowflakeIcon className="kolibri-weather-scene__snow kolibri-weather-scene__snow--two absolute left-[53%] top-[-16%] size-8 stroke-[0.8] text-white/55" />
          <SnowflakeIcon className="kolibri-weather-scene__snow kolibri-weather-scene__snow--three absolute left-[82%] top-[-10%] size-5 stroke-[1] text-white/65" />
        </>
      ) : null}

      {scene === "storm" ? (
        <div className="kolibri-weather-scene__flash absolute inset-0 bg-white" />
      ) : null}
    </div>
  );
}

const iconForWeather = (code?: number, condition = "") => {
  const coded = WEATHER_ICONS.find(({ codes }) =>
    typeof code === "number" ? codes.includes(code) : false,
  )?.icon;
  if (coded) return coded;

  const normalized = condition.toLocaleLowerCase("ru-RU");
  if (/(гроз|thunder)/.test(normalized)) return CloudLightningIcon;
  if (/(снег|snow)/.test(normalized)) return CloudSnowIcon;
  if (/(дожд|лив|морос|rain|shower|drizzle)/.test(normalized)) {
    return CloudRainIcon;
  }
  if (/(туман|fog|mist)/.test(normalized)) return CloudFogIcon;
  if (/(ясн|солнеч|clear|sunny)/.test(normalized)) return SunIcon;
  return CloudIcon;
};

const formatTemperature = (value: number) => `${Math.round(value)}°`;

const formatForecastDay = (date: string, index: number) => {
  if (index === 0) return "Сегодня";
  if (index === 1) return "Завтра";
  const parsed = new Date(`${date}T12:00:00`);
  if (!Number.isFinite(parsed.valueOf())) return date;
  return new Intl.DateTimeFormat("ru-RU", { weekday: "short" })
    .format(parsed)
    .replace(".", "");
};

const formatObservedAt = (value: string) => {
  const parsed = new Date(value);
  if (!Number.isFinite(parsed.valueOf())) return value;
  return new Intl.DateTimeFormat("ru-RU", {
    day: "numeric",
    month: "long",
    hour: "2-digit",
    minute: "2-digit",
  }).format(parsed);
};

export function WeatherWidget(props: WeatherWidgetProps) {
  const widgetRef = useRef<HTMLElement>(null);
  const [sceneActive, setSceneActive] = useState(false);
  const CurrentIcon = iconForWeather(props.weatherCode, props.condition);
  const scene = weatherSceneFor(
    props.weatherCode,
    props.condition,
    props.isDay,
  );
  const forecast = props.forecast ?? [];
  const today = forecast[0];
  const hasDetails =
    props.feelsLike !== undefined ||
    props.humidity !== undefined ||
    props.windSpeed !== undefined ||
    props.precipitation !== undefined;
  const placeDetails = [props.region, props.country]
    .filter((value) => value && value !== props.location)
    .join(", ");

  useEffect(() => {
    const widget = widgetRef.current;
    if (!widget || typeof IntersectionObserver === "undefined") {
      setSceneActive(true);
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        const [entry] = entries;
        if (entry) setSceneActive(entry.isIntersecting);
      },
      { rootMargin: "180px 0px" },
    );
    observer.observe(widget);
    return () => observer.disconnect();
  }, []);

  return (
    <section
      className="relative isolate overflow-hidden rounded-[28px] border border-white/10 bg-[#05080d] text-white shadow-[0_18px_50px_rgba(2,6,23,0.18)]"
      aria-label={`Погода: ${props.location}`}
      data-weather-active={sceneActive ? "true" : "false"}
      ref={widgetRef}
    >
      <WeatherSceneBackdrop active={sceneActive} scene={scene} />
      <div
        aria-hidden="true"
        className={`absolute inset-0 -z-10 ${
          scene === "clear-day" ? "bg-slate-950/35" : "bg-black/40"
        }`}
      />

      <div className="flex min-h-[440px] flex-col p-5 sm:min-h-[540px] sm:p-8">
        <header className="flex min-w-0 items-start justify-between gap-4">
          <div className="min-w-0">
            <h3 className="truncate text-2xl font-medium tracking-[-0.025em] sm:text-[28px]">
              {props.location}
            </h3>
            <p className="mt-1 truncate text-sm text-white/65">
              {[placeDetails, props.condition].filter(Boolean).join(" · ")}
            </p>
          </div>
          <CurrentIcon
            aria-hidden="true"
            className={`kolibri-weather-current-icon mt-1 size-8 shrink-0 stroke-[1.35] text-white/80 ${
              scene === "clear-day"
                ? "kolibri-weather-current-icon--spin"
                : "kolibri-weather-current-icon--float"
            }`}
          />
        </header>

        <div className="mt-5 min-w-0 sm:mt-6">
          {props.temperature !== undefined ? (
            <div className="flex items-start">
              <span className="text-[88px] font-light leading-[0.88] tracking-[-0.075em] tabular-nums sm:text-[112px]">
                {Math.round(props.temperature)}
              </span>
              <span className="ml-2 mt-1 text-[34px] font-light tracking-[-0.04em] text-white/80 sm:mt-2 sm:text-[42px]">
                °C
              </span>
            </div>
          ) : (
            <p className="text-4xl font-light tracking-tight">
              {props.condition}
            </p>
          )}

          {today?.temperatureMax !== undefined ||
          today?.temperatureMin !== undefined ? (
            <div className="mt-5 flex items-center gap-4 text-xl font-medium tabular-nums sm:text-2xl">
              {today.temperatureMax !== undefined ? (
                <span>
                  <span className="mr-2 font-normal text-white/45">H</span>
                  {formatTemperature(today.temperatureMax)}
                </span>
              ) : null}
              {today.temperatureMin !== undefined ? (
                <span>
                  <span className="mr-2 font-normal text-white/45">L</span>
                  {formatTemperature(today.temperatureMin)}
                </span>
              ) : null}
            </div>
          ) : null}

          {hasDetails ? (
            <dl className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-white/60 sm:text-sm">
              {props.feelsLike !== undefined ? (
                <div className="flex items-center gap-1.5">
                  <dt>Ощущается</dt>
                  <dd className="font-medium text-white/90 tabular-nums">
                    {formatTemperature(props.feelsLike)}
                  </dd>
                </div>
              ) : null}
              {props.humidity !== undefined ? (
                <div className="flex items-center gap-1.5">
                  <dt className="flex items-center gap-1">
                    <DropletsIcon aria-hidden="true" className="size-3.5" />
                    Влажность
                  </dt>
                  <dd className="font-medium text-white/90 tabular-nums">
                    {props.humidity}%
                  </dd>
                </div>
              ) : null}
              {props.windSpeed !== undefined ? (
                <div className="flex items-center gap-1.5">
                  <dt className="flex items-center gap-1">
                    <WindIcon aria-hidden="true" className="size-3.5" />
                    Ветер
                  </dt>
                  <dd className="font-medium text-white/90 tabular-nums">
                    {props.windSpeed} км/ч
                  </dd>
                </div>
              ) : null}
              {props.precipitation !== undefined ? (
                <div className="flex items-center gap-1.5">
                  <dt>Осадки</dt>
                  <dd className="font-medium text-white/90 tabular-nums">
                    {props.precipitation} мм
                  </dd>
                </div>
              ) : null}
            </dl>
          ) : null}

          {props.summary ? (
            <p className="sr-only">{props.summary}</p>
          ) : null}
        </div>

        {forecast.length > 0 ? (
          <div className="mt-auto overflow-x-auto rounded-[24px] border border-white/10 bg-[#080b14]/80 px-2 py-5 sm:px-3 sm:py-6">
            <div className="grid min-w-[470px] grid-flow-col auto-cols-fr">
              {forecast.map((day, index) => {
                const ForecastIcon = iconForWeather(
                  day.weatherCode,
                  day.condition,
                );
                return (
                  <div
                    key={day.date}
                    className="flex min-w-[86px] flex-col items-center px-2 text-center"
                  >
                    <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-white/85 sm:text-xs">
                      {formatForecastDay(day.date, index)}
                    </p>
                    <ForecastIcon
                      aria-hidden="true"
                      className="my-3 size-7 stroke-[1.35] text-white/75 sm:size-8"
                    />
                    {day.temperatureMax !== undefined ||
                    day.temperatureMin !== undefined ? (
                      <div className="tabular-nums">
                        <p className="text-lg font-medium sm:text-xl">
                          {day.temperatureMax !== undefined
                            ? formatTemperature(day.temperatureMax)
                            : "—"}
                        </p>
                        <p className="mt-0.5 text-sm font-normal text-white/65 sm:text-base">
                          {day.temperatureMin !== undefined
                            ? formatTemperature(day.temperatureMin)
                            : "—"}
                        </p>
                      </div>
                    ) : (
                      <p className="max-w-20 truncate text-xs font-medium text-white/85">
                        {day.condition}
                      </p>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        ) : null}

        {props.observedAt ||
        props.sourceLabel ||
        (props.sources && props.sources.length > 0) ? (
          <footer className="mt-3 flex flex-wrap items-center justify-between gap-2 px-1 text-[10px] text-white/45">
            <span>
              {props.observedAt
                ? `Данные на ${formatObservedAt(props.observedAt)}`
                : "Ответ выбранной модели"}
            </span>
            <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
              {props.sources?.map((source) =>
                source.sourceUrl ? (
                  <a
                    key={`${source.label}-${source.sourceUrl}`}
                    className="rounded underline-offset-4 hover:text-white/80 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white"
                    href={source.sourceUrl}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {source.label}
                  </a>
                ) : (
                  <span key={source.label}>{source.label}</span>
                ),
              )}
              {props.sourceLabel ? (
                <a
                  className="rounded underline-offset-4 hover:text-white/80 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white"
                  href="https://open-meteo.com/"
                  target="_blank"
                  rel="noreferrer"
                >
                  {props.sourceLabel}
                </a>
              ) : null}
            </span>
          </footer>
        ) : null}
      </div>
    </section>
  );
}

export const WeatherToolUI = makeAssistantToolUI({
  toolName: "get_weather",
  render: ({ args, result, status }) => {
    if (status.type === "running") {
      return (
        <div
          className="rounded-xl border border-border px-4 py-3 text-sm text-muted-foreground"
          role="status"
          aria-live="polite"
        >
          Получаю погоду для{" "}
          {typeof args.location === "string" ? args.location : "города"}…
        </div>
      );
    }

    let decodedResult: unknown = result;
    if (typeof result === "string") {
      try {
        decodedResult = JSON.parse(result) as unknown;
      } catch {
        decodedResult = null;
      }
    }
    if (
      typeof decodedResult === "object" &&
      decodedResult !== null &&
      !Array.isArray(decodedResult) &&
      "$type" in decodedResult &&
      decodedResult.$type === "WeatherWidget"
    ) {
      const { $type: _type, ...weatherProps } = decodedResult;
      decodedResult = weatherProps;
    }
    const parsed =
      kolibriGenerativeUIComponentSchemas.WeatherWidget.safeParse(decodedResult);
    if (!parsed.success) {
      return (
        <div
          className="rounded-xl border border-dashed border-border px-4 py-3 text-sm text-muted-foreground"
          role="alert"
        >
          Погодный сервис вернул данные неизвестного формата.
        </div>
      );
    }
    return <WeatherWidget {...parsed.data} />;
  },
});

const toAmount = (quantity: string, unitPrice: string) => {
  const left = Number(quantity);
  const right = Number(unitPrice);
  if (!Number.isFinite(left) || !Number.isFinite(right)) return 0;
  return Math.round(left * right * 100) / 100;
};

const formatMoney = (value: number | string) => {
  const numeric = typeof value === "number" ? value : Number(value);
  return new Intl.NumberFormat("ru-RU", {
    style: "currency",
    currency: "RUB",
    maximumFractionDigits: 2,
  }).format(Number.isFinite(numeric) ? numeric : 0);
};

const readResponseError = async (response: Response) => {
  if (response.status === 401) announceAuthenticationRequired();
  try {
    const value = (await response.json()) as unknown;
    if (
      typeof value === "object" &&
      value !== null &&
      "message" in value &&
      typeof value.message === "string"
    ) {
      return value.message;
    }
  } catch {
    // A bounded, user-safe fallback is returned below.
  }
  return "Не удалось сохранить смету.";
};

const emptyRow = (): EditableEstimateRow => ({
  id: `row_${globalThis.crypto.randomUUID().replaceAll("-", "")}`,
  section: "Прочее",
  kind: "service",
  description: "",
  unit: "шт.",
  quantity: "1",
  unitPrice: "0.00",
  quantityBasis: "Введено пользователем",
  priceBasis: "Введено пользователем",
  priceEvidence: null,
});

type EstimateEditorWidgetProps = EstimateWidgetProps & {
  presentation?: "canvas" | "inline";
};
type EstimateConflictState = {
  currentVersion: number;
  expectedVersion: number;
  authoritative: EstimateWidgetProps | null;
  diff: EstimateDraftConflictDiff | null;
};

const editableRowsFromEstimate = (estimate: EstimateWidgetProps) =>
  estimate.rows.map(({ lineTotal: _lineTotal, ...row }) => row);

const draftSnapshotFromEstimate = (
  estimate: EstimateWidgetProps,
): EstimateDraftSnapshot => ({
  title: estimate.estimateTitle,
  rows: editableRowsFromEstimate(estimate),
});

function EstimateConflictItems({
  items,
  label,
}: {
  items: readonly string[];
  label: string;
}) {
  if (items.length === 0) return null;
  const visibleItems = items.slice(0, 4);
  return (
    <div className="min-w-0">
      <p className="text-xs font-semibold">{label}</p>
      <ul className="mt-1 space-y-0.5 text-xs text-muted-foreground">
        {visibleItems.map((item) => (
          <li key={item} className="truncate">
            {item}
          </li>
        ))}
        {items.length > visibleItems.length ? (
          <li>Ещё изменений: {items.length - visibleItems.length}</li>
        ) : null}
      </ul>
    </div>
  );
}

const isoDateAfter = (days: number) => {
  const value = new Date();
  value.setDate(value.getDate() + days);
  return value.toISOString().slice(0, 10);
};

const priceSourceLabel = (evidence: PriceEvidence) => {
  if (evidence.status === "stale") return "Цена устарела";
  if (evidence.sourceType === "fgis_cs") return "ФГИС ЦС";
  if (evidence.bindingStatus === "user_attested_binding") {
    return "Предложение поставщика";
  }
  return "Цена поставщика";
};

const enginePriceSourceLabel = (provenance: EnginePriceProvenance) => {
  if (!provenance.verified) return "AI‑кандидат · не проверено";
  if (provenance.sourceType === "regional_catalog") {
    return "Региональный каталог";
  }
  if (provenance.sourceType === "supplier_offer") {
    return "Предложение поставщика";
  }
  if (provenance.sourceType === "organization_price") {
    return "Цена организации";
  }
  return "Цена пользователя";
};

const engineVatLabel = (vatMode: EnginePriceProvenance["vatMode"]) => {
  if (vatMode === "included") return "НДС включён";
  if (vatMode === "excluded") return "без НДС";
  if (vatMode === "not_applicable") return "без НДС";
  return "НДС не указан";
};

const estimateKindLabel = (kind: EditableEstimateRow["kind"]) => {
  if (kind === "work") return "работа";
  if (kind === "material") return "материал";
  if (kind === "equipment") return "оборудование";
  return "услуга";
};

function EstimateRowEvidence({
  row,
  className,
}: {
  row: EditableEstimateRow;
  className?: string;
}) {
  return (
    <details className={className}>
      <summary className="min-h-11 cursor-pointer select-none py-3 font-medium text-foreground">
        Основание количества и цены
      </summary>
      <div className="space-y-1 pb-2 leading-5 text-muted-foreground">
        <p>Количество: {row.quantityBasis}</p>
        <p>Цена: {row.priceBasis}</p>
        {row.priceEvidence ? (
          <>
            <p>
              Регион: {row.priceEvidence.region}
              {row.priceEvidence.period ? ` · ${row.priceEvidence.period}` : ""}
            </p>
            <p>
              {row.priceEvidence.freshnessBasis === "supplier_valid_until"
                ? "Действует до"
                : "Проверить актуальность после"}{" "}
              {row.priceEvidence.freshUntil} ·{" "}
              {row.priceEvidence.taxStatus === "included"
                ? "НДС включён"
                : row.priceEvidence.taxStatus === "excluded"
                  ? "без НДС"
                  : "НДС не указан"}
            </p>
            {row.priceEvidence.landedCostStatus === "not_calculated" ? (
              <p>Справочная цена · доставка и складирование не рассчитаны</p>
            ) : (
              <p>
                Цена с доставкой:{" "}
                {formatMoney(Number(row.priceEvidence.landedUnitPrice))}
              </p>
            )}
            <a
              className="inline-flex text-foreground underline underline-offset-2"
              href={row.priceEvidence.sourceUrl}
              target="_blank"
              rel="noreferrer"
            >
              Источник · {row.priceEvidence.sourceReference}
            </a>
            <p title={row.priceEvidence.snapshotHash}>
              Снимок: {row.priceEvidence.snapshotHash.slice(0, 18)}…
            </p>
          </>
        ) : row.enginePriceProvenance ? (
          <>
            <p
              className={
                row.enginePriceProvenance.verified
                  ? "text-emerald-700 dark:text-emerald-400"
                  : "text-amber-700 dark:text-amber-400"
              }
            >
              {enginePriceSourceLabel(row.enginePriceProvenance)}
            </p>
            <p>
              {row.enginePriceProvenance.label} ·{" "}
              {row.enginePriceProvenance.reference}
            </p>
            <p>
              Регион: {row.enginePriceProvenance.region} · на{" "}
              {row.enginePriceProvenance.observedAt.slice(0, 10)}
            </p>
            <p>
              {engineVatLabel(row.enginePriceProvenance.vatMode)} · уверенность{" "}
              {Math.round(Number(row.enginePriceProvenance.confidence) * 100)}%
            </p>
            {row.enginePriceProvenance.validUntil ? (
              <p>
                Действует до{" "}
                {row.enginePriceProvenance.validUntil.slice(0, 10)}
              </p>
            ) : null}
            {row.enginePriceProvenance.sourceUrl.startsWith("https://") ? (
              <a
                className="inline-flex text-foreground underline underline-offset-2"
                href={row.enginePriceProvenance.sourceUrl}
                target="_blank"
                rel="noreferrer"
              >
                Открыть источник
              </a>
            ) : (
              <p>Источник сохранён в текущем расчёте</p>
            )}
          </>
        ) : (
          <p className="text-amber-700 dark:text-amber-400">
            Цена введена без подтверждённого источника.
          </p>
        )}
      </div>
    </details>
  );
}

function SupplierOfferForm({
  projectId,
  row,
  version,
  onApplied,
}: {
  projectId: string;
  row: EditableEstimateRow;
  version: number;
  onApplied: (estimate: EstimateWidgetProps, message: string) => void;
}) {
  const [supplierName, setSupplierName] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [quoteReference, setQuoteReference] = useState("");
  const [observedOn, setObservedOn] = useState(() => isoDateAfter(0));
  const [validUntil, setValidUntil] = useState(() => isoDateAfter(30));
  const [unitPrice, setUnitPrice] = useState(row.unitPrice);
  const [deliveryPerUnit, setDeliveryPerUnit] = useState("0.00");
  const [vatStatus, setVatStatus] = useState<
    "included" | "excluded" | "unknown"
  >("unknown");
  const [offerKind, setOfferKind] = useState<"indicative" | "binding">(
    "indicative",
  );
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const submit = async () => {
    if (
      !supplierName.trim() ||
      !sourceUrl.trim() ||
      !quoteReference.trim() ||
      !observedOn ||
      !/^(?:0|[1-9]\d{0,11})(?:\.\d{1,2})?$/.test(unitPrice) ||
      !/^(?:0|[1-9]\d{0,11})(?:\.\d{1,2})?$/.test(deliveryPerUnit)
    ) {
      setError("Заполните поставщика, ссылку, номер предложения и цену.");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      const response = await fetch(
        `/api/v3/projects/${encodeURIComponent(projectId)}/estimate/prices/supplier-offers`,
        {
          method: "POST",
          headers: withCsrfHeader({
            Accept: "application/json",
            "Content-Type": "application/json",
            "Idempotency-Key": `supplier-offer-${globalThis.crypto.randomUUID()}`,
          }),
          body: JSON.stringify({
            version,
            rowId: row.id,
            supplierName: supplierName.trim(),
            sourceUrl: sourceUrl.trim(),
            quoteReference: quoteReference.trim(),
            observedOn,
            validUntil: validUntil || null,
            unitPrice,
            deliveryPerUnit,
            vatIncluded:
              vatStatus === "included"
                ? true
                : vatStatus === "excluded"
                  ? false
                  : null,
            offerKind,
            availability: "unknown",
            leadTimeDays: null,
          }),
          credentials: "same-origin",
          cache: "no-store",
        },
      );
      if (!response.ok) {
        throw new Error(await readResponseError(response));
      }
      const value: unknown = await response.json();
      const record =
        typeof value === "object" && value !== null
          ? (value as Record<string, unknown>)
          : null;
      const parsed =
        kolibriGenerativeUIComponentSchemas.EstimateEditor.safeParse(
          record?.estimate,
        );
      if (!parsed.success) {
        throw new Error("Сервер вернул смету неизвестного формата.");
      }
      onApplied(
        parsed.data,
        typeof record?.message === "string"
          ? record.message
          : "Предложение поставщика прикреплено.",
      );
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Не удалось прикрепить предложение.",
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="mt-2 rounded-lg border border-border bg-background p-3">
      <p className="text-xs font-medium text-foreground">
        Предложение для «{row.description}»
      </p>
      <div className="mt-2 grid gap-2 sm:grid-cols-2">
        <Input
          aria-label="Поставщик"
          placeholder="Поставщик"
          value={supplierName}
          maxLength={240}
          onChange={(event) => setSupplierName(event.target.value)}
        />
        <Input
          aria-label="Номер предложения"
          placeholder="КП-2026/41"
          value={quoteReference}
          maxLength={160}
          onChange={(event) => setQuoteReference(event.target.value)}
        />
        <Input
          aria-label="Ссылка на предложение поставщика"
          type="url"
          placeholder="https://supplier.ru/quote/..."
          value={sourceUrl}
          maxLength={1_000}
          onChange={(event) => setSourceUrl(event.target.value)}
        />
        <select
          aria-label="Статус предложения"
          className="h-9 rounded-md border border-input bg-transparent px-3 text-sm"
          value={offerKind}
          onChange={(event) =>
            setOfferKind(event.target.value as "indicative" | "binding")
          }
        >
          <option value="indicative">Ориентировочное</option>
          <option value="binding">
            Заявлено как действующее · не проверено Kolibri
          </option>
        </select>
        <label className="text-[11px] text-muted-foreground">
          Дата предложения
          <Input
            type="date"
            value={observedOn}
            max={new Date().toISOString().slice(0, 10)}
            onChange={(event) => setObservedOn(event.target.value)}
          />
        </label>
        <label className="text-[11px] text-muted-foreground">
          Действует до
          <Input
            type="date"
            value={validUntil}
            required={offerKind === "binding"}
            onChange={(event) => setValidUntil(event.target.value)}
          />
        </label>
        <label className="text-[11px] text-muted-foreground">
          Цена за {row.unit}
          <Input
            inputMode="decimal"
            value={unitPrice}
            onChange={(event) => setUnitPrice(event.target.value)}
          />
        </label>
        <label className="text-[11px] text-muted-foreground">
          Доставка за {row.unit}
          <Input
            inputMode="decimal"
            value={deliveryPerUnit}
            onChange={(event) => setDeliveryPerUnit(event.target.value)}
          />
        </label>
        <select
          aria-label="НДС в предложении"
          className="h-9 rounded-md border border-input bg-transparent px-3 text-sm"
          value={vatStatus}
          onChange={(event) =>
            setVatStatus(
              event.target.value as "included" | "excluded" | "unknown",
            )
          }
        >
          <option value="unknown">НДС не указан</option>
          <option value="included">НДС включён</option>
          <option value="excluded">Без НДС</option>
        </select>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button
          type="button"
          size="sm"
          disabled={submitting}
          onClick={() => void submit()}
        >
          {submitting ? (
            <LoaderCircleIcon className="size-4 animate-spin" />
          ) : (
            <CheckCircle2Icon className="size-4" />
          )}
          Прикрепить цену
        </Button>
        {error ? (
          <span className="text-xs text-destructive" role="alert">
            {error}
          </span>
        ) : (
          <span className="text-xs text-muted-foreground">
            Реквизиты предложения и их hash сохранятся в истории.
          </span>
        )}
      </div>
    </div>
  );
}

export function EstimateEditorWidget({
  presentation = "canvas",
  ...initial
}: EstimateEditorWidgetProps) {
  const hasLocalEdits = useRef(false);
  const savingRef = useRef(false);
  const latestSnapshotRef = useRef("");
  const [version, setVersion] = useState(initial.version);
  const [title, setTitle] = useState(initial.estimateTitle);
  const [region, setRegion] = useState(initial.estimateRegion);
  const [assumptions, setAssumptions] = useState(initial.assumptions);
  const [pricing, setPricing] = useState(initial.pricing);
  const [rows, setRows] = useState<EditableEstimateRow[]>(() =>
    initial.rows.map(({ lineTotal: _lineTotal, ...row }) => row),
  );
  const [savedSnapshot, setSavedSnapshot] = useState(() =>
    JSON.stringify({ title: initial.estimateTitle, rows }),
  );
  const [saveState, setSaveState] = useState<
    "idle" | "saving" | "saved" | "error" | "conflict"
  >("idle");
  const [saveMessage, setSaveMessage] = useState("");
  const [saveRetryAttempt, setSaveRetryAttempt] = useState(0);
  const [saveErrorRetryable, setSaveErrorRetryable] = useState(false);
  const [versionConflict, setVersionConflict] =
    useState<EstimateConflictState | null>(null);
  const [actionMessage, setActionMessage] = useState("");
  const [priceRefreshState, setPriceRefreshState] = useState<
    "idle" | "checking" | "error"
  >("idle");
  const [offerRowId, setOfferRowId] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    const hydrateAuthoritativeEstimate = async () => {
      try {
        const response = await fetch(
          `/api/v3/projects/${encodeURIComponent(initial.projectId)}/estimate`,
          {
            method: "GET",
            headers: { Accept: "application/json" },
            credentials: "same-origin",
            cache: "no-store",
          },
        );
        if (!response.ok) return;

        const value = (await response.json()) as unknown;
        const parsed =
          kolibriGenerativeUIComponentSchemas.EstimateEditor.safeParse(value);
        if (!active || !parsed.success || hasLocalEdits.current) return;

        const nextRows = parsed.data.rows.map(
          ({ lineTotal: _lineTotal, ...row }) => row,
        );
        setVersion(parsed.data.version);
        setTitle(parsed.data.estimateTitle);
        setRegion(parsed.data.estimateRegion);
        setAssumptions(parsed.data.assumptions);
        setPricing(parsed.data.pricing);
        setRows(nextRows);
        setSavedSnapshot(
          JSON.stringify({ title: parsed.data.estimateTitle, rows: nextRows }),
        );
      } catch {
        // The tool-call snapshot remains usable while the authoritative
        // document is temporarily unavailable.
      }
    };

    void hydrateAuthoritativeEstimate();
    return () => {
      active = false;
    };
  }, [initial.projectId]);

  const currentSnapshot = JSON.stringify({ title, rows });
  latestSnapshotRef.current = currentSnapshot;
  const dirty = currentSnapshot !== savedSnapshot;
  const valid =
    title.trim().length > 0 &&
    rows.every(
      (row) =>
        row.description.trim().length > 0 &&
        /^(?:0|[1-9]\d{0,11})(?:\.\d{1,6})?$/.test(row.quantity) &&
        /^(?:0|[1-9]\d{0,11})(?:\.\d{1,2})?$/.test(row.unitPrice),
    );
  const total = useMemo(
    () =>
      rows.reduce(
        (sum, row) => sum + toAmount(row.quantity, row.unitPrice),
        0,
      ),
    [rows],
  );
  const materialRowCount = rows.filter((row) => row.kind === "material").length;
  const pricingLabel =
    pricing.status === "sourced"
      ? `С источником ${pricing.sourcedRows} из ${pricing.totalRows}`
      : pricing.status === "partially_sourced"
        ? `С источником ${pricing.sourcedRows} из ${pricing.totalRows}`
        : pricing.status === "stale"
          ? `Устарело цен: ${pricing.staleRows}`
          : "Источники цен не добавлены";

  useEffect(() => {
    setSaveRetryAttempt(0);
    setSaveErrorRetryable(false);
    setSaveState((current) => (current === "error" ? "idle" : current));
  }, [currentSnapshot]);

  const updateRow = (
    id: string,
    field: "description" | "unit" | "quantity" | "unitPrice",
    value: string,
  ) => {
    hasLocalEdits.current = true;
    setRows((current) =>
      current.map((row) => {
        if (row.id !== id) return row;
        const invalidatesPrice =
          field === "description" ||
          field === "unit" ||
          field === "unitPrice";
        return {
          ...row,
          [field]: value,
          ...(invalidatesPrice
            ? {
                priceBasis: "Введено пользователем",
                priceEvidence: null,
              }
            : null),
        };
      }),
    );
    setSaveState((current) =>
      current === "conflict" ? current : "idle",
    );
  };

  const downloadEstimate = (format: EstimateExportFormat) => {
    const anchor = document.createElement("a");
    anchor.href = `/api/v3/projects/${encodeURIComponent(initial.projectId)}/estimate/export/${format}`;
    anchor.download = "";
    if (format === "zip") {
      anchor.target = "_blank";
      anchor.rel = "noopener noreferrer";
    }
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    setActionMessage(
      `${
        format === "xlsx"
          ? "Excel"
          : format === "docx"
            ? "Word"
            : format === "zip"
              ? "Пакет ZIP"
            : format.toUpperCase()
      } скачивается`,
    );
  };

  const save = useCallback(async () => {
    if (!dirty || !valid || savingRef.current || versionConflict) return;
    const snapshotAtStart = currentSnapshot;
    const versionAtStart = version;
    const titleAtStart = title.trim();
    const rowsAtStart = rows.map(
      ({
        priceEvidence: _priceEvidence,
        enginePriceProvenance: _enginePriceProvenance,
        ...row
      }) => ({
        ...row,
        description: row.description.trim(),
        unit: row.unit.trim(),
      }),
    );
    savingRef.current = true;
    setSaveState("saving");
    setSaveMessage("");
    try {
      const headers = withCsrfHeader({
        Accept: "application/json",
        "Content-Type": "application/json",
      });
      const response = await fetch(
        `/api/v3/projects/${encodeURIComponent(initial.projectId)}/estimate`,
        {
          method: "PATCH",
          headers,
          body: JSON.stringify({
            version: versionAtStart,
            title: titleAtStart,
            currency: initial.currency,
            rows: rowsAtStart,
          }),
          credentials: "same-origin",
          cache: "no-store",
        },
      );
      if (!response.ok) {
        let errorPayload: unknown = null;
        try {
          errorPayload = await response.clone().json();
        } catch {
          // The bounded fallback below remains available for non-JSON errors.
        }
        const conflict = parseEstimateVersionConflict(
          response.status,
          errorPayload,
        );
        if (conflict) {
          let authoritative: EstimateWidgetProps | null = null;
          try {
            authoritative = await loadEstimateDocument(initial.projectId);
          } catch {
            // Keep the local draft even when the current server copy cannot
            // be loaded yet. The user can retry the comparison explicitly.
          }
          const baseline = JSON.parse(
            savedSnapshot,
          ) as EstimateDraftSnapshot;
          const local = JSON.parse(
            latestSnapshotRef.current,
          ) as EstimateDraftSnapshot;
          const currentVersion =
            authoritative?.version ?? conflict.currentVersion;
          setVersionConflict({
            ...conflict,
            currentVersion,
            authoritative,
            diff: authoritative
              ? diffEstimateDrafts(
                  baseline,
                  local,
                  draftSnapshotFromEstimate(authoritative),
                )
              : null,
          });
          setSaveMessage(
            authoritative
              ? `Серверная версия ${currentVersion} загружена для сравнения. Локальный черновик не изменён.`
              : `На сервере уже версия ${currentVersion}. Локальный черновик не изменён; повторите загрузку сравнения.`,
          );
          setSaveErrorRetryable(false);
          setSaveState("conflict");
          return;
        }
        setSaveMessage(await readResponseError(response));
        setSaveErrorRetryable(
          response.status === 408 ||
            response.status === 429 ||
            response.status >= 500,
        );
        setSaveRetryAttempt((current) => current + 1);
        setSaveState("error");
        return;
      }
      const value = (await response.json()) as unknown;
      const parsed =
        kolibriGenerativeUIComponentSchemas.EstimateEditor.safeParse(value);
      if (!parsed.success) {
        setSaveMessage("Сервер вернул смету неизвестного формата.");
        setSaveErrorRetryable(false);
        setSaveState("error");
        return;
      }
      const nextRows = parsed.data.rows.map(
        ({ lineTotal: _lineTotal, ...row }) => row,
      );
      const nextSavedSnapshot = JSON.stringify({
        title: parsed.data.estimateTitle,
        rows: nextRows,
      });
      const noNewEdits = latestSnapshotRef.current === snapshotAtStart;
      setVersion(parsed.data.version);
      setRegion(parsed.data.estimateRegion);
      setAssumptions(parsed.data.assumptions);
      setPricing(parsed.data.pricing);
      setSavedSnapshot(nextSavedSnapshot);
      if (noNewEdits) {
        setTitle(parsed.data.estimateTitle);
        setRows(nextRows);
        hasLocalEdits.current = false;
      }
      announceDocumentsChanged();
      setSaveRetryAttempt(0);
      setSaveErrorRetryable(false);
      setSaveState(noNewEdits ? "saved" : "idle");
    } catch {
      setSaveMessage("Нет связи с сервером. Изменения остались в редакторе.");
      setSaveErrorRetryable(true);
      setSaveRetryAttempt((current) => current + 1);
      setSaveState("error");
    } finally {
      savingRef.current = false;
    }
  }, [
    currentSnapshot,
    dirty,
    initial.currency,
    initial.projectId,
    rows,
    savedSnapshot,
    title,
    valid,
    version,
    versionConflict,
  ]);

  const refreshVersionConflict = useCallback(async () => {
    if (!versionConflict) return;
    setSaveMessage("Загружаю текущую серверную версию для сравнения…");
    try {
      const authoritative = await loadEstimateDocument(initial.projectId);
      const baseline = JSON.parse(savedSnapshot) as EstimateDraftSnapshot;
      const local = JSON.parse(
        latestSnapshotRef.current,
      ) as EstimateDraftSnapshot;
      setVersionConflict((current) =>
        current
          ? {
              ...current,
              authoritative,
              currentVersion: authoritative.version,
              diff: diffEstimateDrafts(
                baseline,
                local,
                draftSnapshotFromEstimate(authoritative),
              ),
            }
          : null,
      );
      setSaveMessage(
        `Серверная версия ${authoritative.version} загружена. Локальный черновик не изменён.`,
      );
    } catch {
      setSaveMessage(
        "Не удалось загрузить серверную версию. Локальный черновик остаётся в редакторе.",
      );
    }
  }, [initial.projectId, savedSnapshot, versionConflict]);

  const useAuthoritativeVersion = useCallback(() => {
    const authoritative = versionConflict?.authoritative;
    if (!authoritative) return;
    const nextRows = editableRowsFromEstimate(authoritative);
    const nextSnapshot = JSON.stringify({
      title: authoritative.estimateTitle,
      rows: nextRows,
    });
    setVersion(authoritative.version);
    setTitle(authoritative.estimateTitle);
    setRegion(authoritative.estimateRegion);
    setAssumptions(authoritative.assumptions);
    setPricing(authoritative.pricing);
    setRows(nextRows);
    setSavedSnapshot(nextSnapshot);
    hasLocalEdits.current = false;
    setVersionConflict(null);
    setSaveMessage("");
    setSaveRetryAttempt(0);
    setSaveErrorRetryable(false);
    setSaveState("saved");
  }, [versionConflict]);

  const rebaseLocalDraft = useCallback(() => {
    const authoritative = versionConflict?.authoritative;
    if (!authoritative) return;
    setVersion(authoritative.version);
    setRegion(authoritative.estimateRegion);
    setAssumptions(authoritative.assumptions);
    setPricing(authoritative.pricing);
    setSavedSnapshot(
      JSON.stringify(draftSnapshotFromEstimate(authoritative)),
    );
    hasLocalEdits.current = true;
    setVersionConflict(null);
    setSaveMessage("");
    setSaveRetryAttempt(0);
    setSaveErrorRetryable(false);
    setSaveState("idle");
  }, [versionConflict]);

  const applyPricedEstimate = useCallback(
    (next: EstimateWidgetProps, message: string) => {
      const nextRows = next.rows.map(
        ({ lineTotal: _lineTotal, ...row }) => row,
      );
      setVersion(next.version);
      setTitle(next.estimateTitle);
      setRegion(next.estimateRegion);
      setAssumptions(next.assumptions);
      setPricing(next.pricing);
      setRows(nextRows);
      setSavedSnapshot(
        JSON.stringify({ title: next.estimateTitle, rows: nextRows }),
      );
      hasLocalEdits.current = false;
      setSaveState("saved");
      setActionMessage(message);
      setOfferRowId(null);
      announceDocumentsChanged();
    },
    [],
  );

  const refreshOfficialPrices = useCallback(async () => {
    if (dirty || priceRefreshState === "checking") return;
    setPriceRefreshState("checking");
    setActionMessage("Проверяю материалы по ФГИС ЦС…");
    try {
      const response = await fetch(
        `/api/v3/projects/${encodeURIComponent(initial.projectId)}/estimate/prices/refresh`,
        {
          method: "POST",
          headers: withCsrfHeader({
            Accept: "application/json",
            "Content-Type": "application/json",
            "Idempotency-Key": `fgis-refresh-${globalThis.crypto.randomUUID()}`,
          }),
          body: JSON.stringify({ version }),
          credentials: "same-origin",
          cache: "no-store",
        },
      );
      if (!response.ok) {
        throw new Error(await readResponseError(response));
      }
      const value: unknown = await response.json();
      const record =
        typeof value === "object" && value !== null
          ? (value as Record<string, unknown>)
          : null;
      const parsed =
        kolibriGenerativeUIComponentSchemas.EstimateEditor.safeParse(
          record?.estimate,
        );
      if (!parsed.success) {
        throw new Error("Сервер вернул смету неизвестного формата.");
      }
      applyPricedEstimate(
        parsed.data,
        typeof record?.message === "string"
          ? record.message
          : "Проверка цен завершена.",
      );
      setPriceRefreshState("idle");
    } catch (caught) {
      setActionMessage(
        caught instanceof Error
          ? caught.message
          : "Не удалось проверить цены.",
      );
      setPriceRefreshState("error");
    }
  }, [
    applyPricedEstimate,
    dirty,
    initial.projectId,
    priceRefreshState,
    version,
  ]);

  useEffect(() => {
    if (
      !dirty ||
      !valid ||
      saveState === "saving" ||
      saveState === "conflict" ||
      versionConflict
    ) {
      return;
    }
    if (saveState === "error" && !saveErrorRetryable) return;
    const retryDelay =
      saveState === "error"
        ? Math.min(1_000 * 2 ** Math.max(0, saveRetryAttempt - 1), 10_000)
        : 700;
    const timeout = window.setTimeout(() => void save(), retryDelay);
    return () => window.clearTimeout(timeout);
  }, [
    dirty,
    save,
    saveErrorRetryable,
    saveRetryAttempt,
    saveState,
    valid,
    versionConflict,
  ]);

  return (
    <section
      data-slot="estimate-editor"
      className={
        presentation === "inline"
          ? "overflow-visible border-t border-border bg-card min-[960px]:overflow-hidden"
          : "overflow-visible border border-border bg-card min-[960px]:overflow-hidden min-[960px]:rounded-xl"
      }
      aria-label="Редактор сметы"
    >
      <header className="grid items-start gap-3 border-b border-border px-4 py-3 min-[960px]:grid-cols-[minmax(0,1fr)_auto]">
        <div className="min-w-0 flex-1">
          <label className="sr-only" htmlFor={`estimate-title-${initial.documentId}`}>
            Название сметы
          </label>
          <input
            id={`estimate-title-${initial.documentId}`}
            className="min-h-11 w-full rounded-md bg-transparent px-1 py-1 text-base font-semibold outline-none focus-visible:ring-2 focus-visible:ring-ring min-[960px]:min-h-0 min-[960px]:py-0.5 min-[960px]:text-sm"
            value={title}
            maxLength={240}
            onChange={(event) => {
              hasLocalEdits.current = true;
              setTitle(event.target.value);
              setSaveState((current) =>
                current === "conflict" ? current : "idle",
              );
            }}
          />
          <p className="mt-0.5 px-1 text-xs text-muted-foreground">
            Черновик · версия {version}
            {region ? ` · ${region}` : ""}
          </p>
        </div>
        <div className="rounded-2xl bg-muted/40 px-3 py-2 text-left min-[960px]:bg-transparent min-[960px]:p-0 min-[960px]:text-right">
          <p className="text-[11px] text-muted-foreground">Итого</p>
          <p className="text-lg font-semibold tabular-nums">
            {formatMoney(total)}
          </p>
        </div>
      </header>

      {versionConflict ? (
        <section
          data-slot="estimate-version-conflict"
          className="border-b border-amber-300 bg-amber-50 px-4 py-4 text-amber-950 dark:border-amber-900 dark:bg-amber-950/35 dark:text-amber-100"
          role="alert"
          aria-live="assertive"
        >
          <div className="flex items-start gap-3">
            <RefreshCwIcon
              aria-hidden="true"
              className="mt-0.5 size-4 shrink-0"
            />
            <div className="min-w-0 flex-1">
              <h3 className="text-sm font-semibold">
                Смета изменилась в другом окне
              </h3>
              <p className="mt-1 text-xs leading-5">
                Редактор открыт на версии {versionConflict.expectedVersion},
                сервер уже на версии {versionConflict.currentVersion}. Ваш
                локальный черновик сохранён в редакторе и не был заменён.
              </p>
              {versionConflict.diff ? (
                <div
                  data-slot="estimate-conflict-diff"
                  className="mt-3 grid gap-3 rounded-xl border border-amber-300/70 bg-background/70 p-3 text-foreground min-[700px]:grid-cols-3 dark:border-amber-800"
                >
                  <EstimateConflictItems
                    items={versionConflict.diff.localChanges}
                    label="В вашем черновике"
                  />
                  <EstimateConflictItems
                    items={versionConflict.diff.remoteChanges}
                    label="На сервере"
                  />
                  <EstimateConflictItems
                    items={versionConflict.diff.conflicts}
                    label="Требуют выбора"
                  />
                  {versionConflict.diff.localChanges.length === 0 &&
                  versionConflict.diff.remoteChanges.length === 0 ? (
                    <p className="text-xs text-muted-foreground">
                      Содержимое совпадает; различается только номер версии.
                    </p>
                  ) : null}
                </div>
              ) : (
                <p className="mt-2 text-xs">{saveMessage}</p>
              )}
              <div className="mt-3 flex flex-col gap-2 min-[700px]:flex-row min-[700px]:flex-wrap">
                {versionConflict.authoritative ? (
                  <>
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={useAuthoritativeVersion}
                    >
                      Загрузить версию {versionConflict.currentVersion}
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      onClick={rebaseLocalDraft}
                    >
                      Сохранить мой черновик поверх версии{" "}
                      {versionConflict.currentVersion}
                    </Button>
                  </>
                ) : (
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() => void refreshVersionConflict()}
                  >
                    Повторить загрузку сравнения
                  </Button>
                )}
              </div>
              {versionConflict.authoritative ? (
                <p className="mt-2 text-[11px] leading-4 text-muted-foreground">
                  Загрузка серверной версии заменит поля редактора. Сохранение
                  черновика создаст следующую версию после явного выбора.
                </p>
              ) : null}
            </div>
          </div>
        </section>
      ) : null}

      <div className="flex flex-col items-stretch gap-2 border-b border-border bg-muted/15 px-4 py-3 min-[960px]:flex-row min-[960px]:items-center min-[960px]:justify-between min-[960px]:py-2.5">
        <div className="flex min-w-0 items-center gap-2 text-xs">
          {priceRefreshState === "checking" ? (
            <LoaderCircleIcon
              aria-hidden="true"
              className="size-4 shrink-0 animate-spin text-muted-foreground"
            />
          ) : pricing.status === "sourced" ? (
            <CheckCircle2Icon
              aria-hidden="true"
              className="size-4 shrink-0 text-emerald-600"
            />
          ) : (
            <RefreshCwIcon
              aria-hidden="true"
              className="size-4 shrink-0 text-muted-foreground"
            />
          )}
          <span className="truncate text-muted-foreground">{pricingLabel}</span>
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={
            dirty ||
            materialRowCount === 0 ||
            priceRefreshState === "checking"
          }
          onClick={() => void refreshOfficialPrices()}
          className="min-h-11 w-full min-[960px]:min-h-0 min-[960px]:w-auto"
        >
          <RefreshCwIcon
            aria-hidden="true"
            className={`size-4 ${
              priceRefreshState === "checking" ? "animate-spin" : ""
            }`}
          />
          Проверить цены материалов
        </Button>
      </div>

      {assumptions.length > 0 ? (
        <div className="border-b border-border bg-muted/20 px-4 py-2.5 text-xs">
          <details>
            <summary className="cursor-pointer select-none font-medium text-foreground">
              Предварительный расчёт · допущений: {assumptions.length}
            </summary>
            <ul className="mt-2 space-y-1 pl-4 text-muted-foreground">
              {assumptions.map((assumption) => (
                <li key={assumption} className="list-disc">
                  {assumption}
                </li>
              ))}
            </ul>
          </details>
        </div>
      ) : null}

      <div
        data-slot="estimate-mobile-list"
        className="space-y-3 bg-muted/10 p-3 pb-28 min-[960px]:hidden"
      >
        {rows.length === 0 ? (
          <div className="rounded-3xl border border-dashed border-border bg-background px-5 py-10 text-center text-sm text-muted-foreground">
            Позиций пока нет. Добавьте первую строку — расчёт появится
            автоматически.
          </div>
        ) : (
          rows.map((row, index) => (
            <article
              key={row.id}
              className="overflow-hidden rounded-3xl border border-border bg-background p-4 shadow-sm"
              aria-labelledby={`estimate-mobile-row-${row.id}`}
            >
              <div className="flex min-w-0 items-start gap-2">
                <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-muted text-sm font-semibold tabular-nums">
                  {index + 1}
                </span>
                <div className="min-w-0 flex-1 pt-0.5">
                  <p
                    id={`estimate-mobile-row-${row.id}`}
                    className="truncate text-xs font-semibold tracking-wide text-muted-foreground uppercase"
                  >
                    {row.section} · {estimateKindLabel(row.kind)}
                  </p>
                  <p
                    className={cn(
                      "mt-1 truncate text-xs",
                      row.priceEvidence?.status === "stale" ||
                        (!row.priceEvidence &&
                          !row.enginePriceProvenance?.verified)
                        ? "text-amber-700 dark:text-amber-400"
                        : "text-emerald-700 dark:text-emerald-400",
                    )}
                  >
                    {row.priceEvidence
                      ? priceSourceLabel(row.priceEvidence)
                      : row.enginePriceProvenance
                        ? enginePriceSourceLabel(row.enginePriceProvenance)
                        : "Источник не указан"}
                  </p>
                </div>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="size-11 shrink-0 rounded-full"
                  aria-label={`Удалить позицию ${index + 1}`}
                  onClick={() => {
                    hasLocalEdits.current = true;
                    setRows((current) =>
                      current.filter((item) => item.id !== row.id),
                    );
                    setSaveState((current) =>
                      current === "conflict" ? current : "idle",
                    );
                  }}
                >
                  <Trash2Icon aria-hidden="true" className="size-5" />
                </Button>
              </div>

              <label className="mt-3 block text-xs font-medium text-muted-foreground">
                Работа или материал
                <input
                  aria-label={`Наименование позиции ${index + 1}`}
                  className="mt-1 min-h-12 w-full rounded-2xl border border-input bg-background px-3 py-2 text-base outline-none focus:ring-2 focus:ring-ring"
                  placeholder="Введите наименование"
                  value={row.description}
                  maxLength={300}
                  enterKeyHint="next"
                  onChange={(event) =>
                    updateRow(row.id, "description", event.target.value)
                  }
                />
              </label>

              <div className="mt-3 grid grid-cols-2 gap-2.5">
                <label className="text-xs font-medium text-muted-foreground">
                  Единица
                  <input
                    aria-label={`Единица позиции ${index + 1}`}
                    className="mt-1 min-h-12 w-full rounded-2xl border border-input bg-background px-3 py-2 text-base text-foreground outline-none focus:ring-2 focus:ring-ring"
                    value={row.unit}
                    maxLength={32}
                    enterKeyHint="next"
                    onChange={(event) =>
                      updateRow(row.id, "unit", event.target.value)
                    }
                  />
                </label>
                <label className="text-xs font-medium text-muted-foreground">
                  Количество
                  <input
                    aria-label={`Количество позиции ${index + 1}`}
                    inputMode="decimal"
                    enterKeyHint="next"
                    className="mt-1 min-h-12 w-full rounded-2xl border border-input bg-background px-3 py-2 text-right text-base text-foreground tabular-nums outline-none focus:ring-2 focus:ring-ring"
                    value={row.quantity}
                    onChange={(event) =>
                      updateRow(row.id, "quantity", event.target.value)
                    }
                  />
                </label>
                <label className="text-xs font-medium text-muted-foreground">
                  Цена
                  <input
                    aria-label={`Цена позиции ${index + 1}`}
                    inputMode="decimal"
                    enterKeyHint="done"
                    className="mt-1 min-h-12 w-full rounded-2xl border border-input bg-background px-3 py-2 text-right text-base text-foreground tabular-nums outline-none focus:ring-2 focus:ring-ring"
                    value={row.unitPrice}
                    onChange={(event) =>
                      updateRow(row.id, "unitPrice", event.target.value)
                    }
                  />
                </label>
                <div className="text-xs font-medium text-muted-foreground">
                  Сумма
                  <output className="mt-1 flex min-h-12 items-center justify-end rounded-2xl bg-muted px-3 py-2 text-base font-semibold text-foreground tabular-nums">
                    {formatMoney(toAmount(row.quantity, row.unitPrice))}
                  </output>
                </div>
              </div>

              <EstimateRowEvidence
                row={row}
                className="mt-2 border-t border-border text-xs"
              />

              <Button
                type="button"
                variant="outline"
                className="min-h-11 w-full rounded-2xl"
                disabled={dirty}
                onClick={() =>
                  setOfferRowId((current) =>
                    current === row.id ? null : row.id,
                  )
                }
              >
                {offerRowId === row.id
                  ? "Скрыть предложение"
                  : "Цена поставщика"}
              </Button>

              {offerRowId === row.id ? (
                <SupplierOfferForm
                  projectId={initial.projectId}
                  row={row}
                  version={version}
                  onApplied={applyPricedEstimate}
                />
              ) : null}
            </article>
          ))
        )}
      </div>

      <div className="hidden overflow-x-auto min-[960px]:block">
        <table className="w-full min-w-[700px] border-collapse text-sm">
          <caption className="sr-only">
            Редактируемые позиции сметы
          </caption>
          <thead>
            <tr className="border-b border-border bg-muted/30 text-left text-[11px] font-medium text-muted-foreground">
              <th className="w-10 px-2 py-2 text-center">№</th>
              <th className="min-w-64 px-2 py-2">Работа или материал</th>
              <th className="w-24 px-2 py-2">Ед.</th>
              <th className="w-28 px-2 py-2 text-right">Кол-во</th>
              <th className="w-36 px-2 py-2 text-right">Цена</th>
              <th className="w-36 px-2 py-2 text-right">Сумма</th>
              <th className="w-10 px-1 py-2">
                <span className="sr-only">Действия</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td
                  colSpan={7}
                  className="px-4 py-8 text-center text-sm text-muted-foreground"
                >
                  Позиций пока нет. Добавьте первую строку — расчёт появится
                  автоматически.
                </td>
              </tr>
            ) : (
              rows.map((row, index) => (
                <Fragment key={row.id}>
                <tr className="border-b border-border last:border-0">
                  <td className="px-2 py-1.5 text-center text-xs text-muted-foreground">
                    {index + 1}
                  </td>
                  <td className="px-2 py-1.5">
                    <div className="mb-0.5 flex items-center gap-2 px-2 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                      <span>{row.section}</span>
                      <span aria-hidden="true">·</span>
                      <span>
                        {row.kind === "work"
                          ? "работа"
                          : row.kind === "material"
                            ? "материал"
                            : row.kind === "equipment"
                              ? "оборудование"
                              : "услуга"}
                      </span>
                      {row.priceEvidence ? (
                        <>
                          <span aria-hidden="true">·</span>
                          <span
                            className={
                              row.priceEvidence.status === "stale"
                                ? "text-amber-700"
                                : "text-emerald-700"
                            }
                          >
                            {priceSourceLabel(row.priceEvidence)}
                          </span>
                        </>
                      ) : row.enginePriceProvenance ? (
                        <>
                          <span aria-hidden="true">·</span>
                          <span
                            className={
                              row.enginePriceProvenance.verified
                                ? "text-emerald-700"
                                : "text-amber-700"
                            }
                          >
                            {enginePriceSourceLabel(
                              row.enginePriceProvenance,
                            )}
                          </span>
                        </>
                      ) : (
                        <>
                          <span aria-hidden="true">·</span>
                          <span className="text-amber-700">
                            Источник не указан
                          </span>
                        </>
                      )}
                    </div>
                    <input
                      aria-label={`Наименование позиции ${index + 1}`}
                      className="w-full rounded-md border border-transparent bg-transparent px-2 py-1.5 outline-none hover:border-border focus:border-border focus:ring-2 focus:ring-ring"
                      placeholder="Введите наименование"
                      value={row.description}
                      maxLength={300}
                      onChange={(event) =>
                        updateRow(row.id, "description", event.target.value)
                      }
                    />
                    <details className="px-2 pt-0.5 text-[10px] text-muted-foreground">
                      <summary className="cursor-pointer select-none">
                        Основание количества и цены
                      </summary>
                      <p className="mt-1">
                        Количество: {row.quantityBasis}
                      </p>
                      <p>Цена: {row.priceBasis}</p>
                      {row.priceEvidence ? (
                        <div className="mt-1 space-y-0.5">
                          <p>
                            Регион: {row.priceEvidence.region}
                            {row.priceEvidence.period
                              ? ` · ${row.priceEvidence.period}`
                              : ""}
                          </p>
                          <p>
                            {row.priceEvidence.freshnessBasis ===
                            "supplier_valid_until"
                              ? "Действует до"
                              : "Проверить актуальность после"}{" "}
                            {row.priceEvidence.freshUntil} ·{" "}
                            {row.priceEvidence.taxStatus === "included"
                              ? "НДС включён"
                              : row.priceEvidence.taxStatus === "excluded"
                                ? "без НДС"
                                : "НДС не указан"}
                          </p>
                          {row.priceEvidence.landedCostStatus ===
                          "not_calculated" ? (
                            <p>
                              Справочная цена · доставка и складирование не
                              рассчитаны
                            </p>
                          ) : (
                            <p>
                              Цена с доставкой:{" "}
                              {formatMoney(
                                Number(row.priceEvidence.landedUnitPrice),
                              )}
                            </p>
                          )}
                          <a
                            className="inline-flex text-foreground underline underline-offset-2"
                            href={row.priceEvidence.sourceUrl}
                            target="_blank"
                            rel="noreferrer"
                          >
                            Источник · {row.priceEvidence.sourceReference}
                          </a>
                          <p title={row.priceEvidence.snapshotHash}>
                            Снимок: {row.priceEvidence.snapshotHash.slice(0, 18)}…
                          </p>
                        </div>
                      ) : row.enginePriceProvenance ? (
                        <div className="mt-1 space-y-0.5">
                          <p
                            className={
                              row.enginePriceProvenance.verified
                                ? "text-emerald-700"
                                : "text-amber-700"
                            }
                          >
                            {enginePriceSourceLabel(
                              row.enginePriceProvenance,
                            )}
                          </p>
                          <p>
                            {row.enginePriceProvenance.label} ·{" "}
                            {row.enginePriceProvenance.reference}
                          </p>
                          <p>
                            Регион: {row.enginePriceProvenance.region} · на{" "}
                            {row.enginePriceProvenance.observedAt.slice(0, 10)}
                          </p>
                          <p>
                            {engineVatLabel(
                              row.enginePriceProvenance.vatMode,
                            )}{" "}
                            · уверенность{" "}
                            {Math.round(
                              Number(row.enginePriceProvenance.confidence) * 100,
                            )}
                            %
                          </p>
                          {row.enginePriceProvenance.validUntil ? (
                            <p>
                              Действует до{" "}
                              {row.enginePriceProvenance.validUntil.slice(0, 10)}
                            </p>
                          ) : null}
                          {row.enginePriceProvenance.sourceUrl.startsWith(
                            "https://",
                          ) ? (
                            <a
                              className="inline-flex text-foreground underline underline-offset-2"
                              href={row.enginePriceProvenance.sourceUrl}
                              target="_blank"
                              rel="noreferrer"
                            >
                              Открыть источник
                            </a>
                          ) : (
                            <p>Источник сохранён в текущем расчёте</p>
                          )}
                        </div>
                      ) : (
                        <p className="mt-1 text-amber-700">
                          Цена введена без подтверждённого источника.
                        </p>
                      )}
                    </details>
                    <div className="px-2 pt-1">
                      <Button
                        type="button"
                        variant="ghost"
                        size="xs"
                        disabled={dirty}
                        onClick={() =>
                          setOfferRowId((current) =>
                            current === row.id ? null : row.id,
                          )
                        }
                      >
                        {offerRowId === row.id
                          ? "Скрыть предложение"
                          : "Цена поставщика"}
                      </Button>
                    </div>
                  </td>
                  <td className="px-2 py-1.5">
                    <input
                      aria-label={`Единица позиции ${index + 1}`}
                      className="w-full rounded-md border border-transparent bg-transparent px-2 py-1.5 outline-none hover:border-border focus:border-border focus:ring-2 focus:ring-ring"
                      value={row.unit}
                      maxLength={32}
                      onChange={(event) =>
                        updateRow(row.id, "unit", event.target.value)
                      }
                    />
                  </td>
                  <td className="px-2 py-1.5">
                    <input
                      aria-label={`Количество позиции ${index + 1}`}
                      inputMode="decimal"
                      className="w-full rounded-md border border-transparent bg-transparent px-2 py-1.5 text-right tabular-nums outline-none hover:border-border focus:border-border focus:ring-2 focus:ring-ring"
                      value={row.quantity}
                      onChange={(event) =>
                        updateRow(row.id, "quantity", event.target.value)
                      }
                    />
                  </td>
                  <td className="px-2 py-1.5">
                    <input
                      aria-label={`Цена позиции ${index + 1}`}
                      inputMode="decimal"
                      className="w-full rounded-md border border-transparent bg-transparent px-2 py-1.5 text-right tabular-nums outline-none hover:border-border focus:border-border focus:ring-2 focus:ring-ring"
                      value={row.unitPrice}
                      onChange={(event) =>
                        updateRow(row.id, "unitPrice", event.target.value)
                      }
                    />
                  </td>
                  <td className="px-2 py-1.5 text-right font-medium tabular-nums">
                    {formatMoney(toAmount(row.quantity, row.unitPrice))}
                  </td>
                  <td className="px-1 py-1.5">
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon-sm"
                      aria-label={`Удалить позицию ${index + 1}`}
                      onClick={() => {
                        hasLocalEdits.current = true;
                        setRows((current) =>
                          current.filter((item) => item.id !== row.id),
                        );
                        setSaveState((current) =>
                          current === "conflict" ? current : "idle",
                        );
                      }}
                    >
                      <Trash2Icon aria-hidden="true" className="size-4" />
                    </Button>
                  </td>
                </tr>
                {offerRowId === row.id ? (
                  <tr className="border-b border-border bg-muted/10">
                    <td colSpan={7} className="px-4 py-3">
                      <SupplierOfferForm
                        projectId={initial.projectId}
                        row={row}
                        version={version}
                        onApplied={applyPricedEstimate}
                      />
                    </td>
                  </tr>
                ) : null}
                </Fragment>
              ))
            )}
          </tbody>
        </table>
      </div>

      <footer
        data-slot="estimate-editor-footer"
        className="sticky bottom-0 z-20 flex flex-wrap items-center justify-between gap-3 border-t border-border bg-card px-4 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] min-[960px]:static min-[960px]:pb-3"
      >
        <div
          data-slot="estimate-editor-footer-actions"
          className="flex min-w-0 flex-wrap items-center gap-2"
        >
          <Button
            data-slot="estimate-add-row-action"
            type="button"
            variant="outline"
            size="sm"
            className="min-h-11 flex-1 rounded-2xl min-[960px]:min-h-0 min-[960px]:flex-none min-[960px]:rounded-md"
            onClick={() => {
              hasLocalEdits.current = true;
              setRows((current) => [...current, emptyRow()]);
              setSaveState((current) =>
                current === "conflict" ? current : "idle",
              );
            }}
          >
            <PlusIcon aria-hidden="true" className="size-4" />
            Позиция
          </Button>
          <span
            className={`min-w-0 flex-1 text-xs ${
              saveState === "error"
                ? "text-destructive"
                : versionConflict
                  ? "text-amber-700 dark:text-amber-300"
                : "text-muted-foreground"
            }`}
            role={saveState === "error" || versionConflict ? "alert" : "status"}
          >
            {saveState === "saving" ? (
              <LoaderCircleIcon
                aria-hidden="true"
                className="size-3.5 shrink-0 animate-spin"
              />
            ) : null}
            {versionConflict
              ? `Нужно выбрать версию · локальный черновик сохранён`
              : saveState === "error"
              ? saveMessage
              : saveState === "saving"
                ? "Сохраняю изменения…"
              : saveState === "saved"
                ? `Автосохранено · версия ${version}`
                : dirty
                  ? valid
                    ? "Сохранится автоматически"
                    : "Заполните наименование и числовые поля"
                  : `Автосохранение включено · версия ${version}`}
          </span>
          {saveState === "error" ? (
            <Button
              type="button"
              variant="ghost"
              size="xs"
              onClick={() => void save()}
            >
              Повторить сохранение
            </Button>
          ) : null}
        </div>
      </footer>
      {rows.length > 0 && !dirty ? (
        <div className="flex flex-col items-stretch gap-2 border-t border-border bg-muted/15 px-4 py-3 min-[960px]:flex-row min-[960px]:items-center min-[960px]:justify-between min-[960px]:py-2.5">
          <div className="flex min-w-0 items-center gap-2 text-xs text-muted-foreground">
            <CheckCircle2Icon
              aria-hidden="true"
              className="size-4 shrink-0 text-emerald-600"
            />
            <span className="truncate">
              {actionMessage || `Сохранено в проекте · версия ${version}`}
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-2 [&>button]:w-full min-[960px]:[&>button]:w-auto">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button type="button" variant="outline" size="sm">
                  <DownloadIcon aria-hidden="true" className="size-4" />
                  Скачать
                  <ChevronDownIcon aria-hidden="true" className="size-3.5" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuLabel className="text-xs">
                  Формат файла
                </DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem onSelect={() => downloadEstimate("pdf")}>
                  PDF
                </DropdownMenuItem>
                <DropdownMenuItem onSelect={() => downloadEstimate("xlsx")}>
                  Excel
                </DropdownMenuItem>
                <DropdownMenuItem onSelect={() => downloadEstimate("docx")}>
                  Word
                </DropdownMenuItem>
                <DropdownMenuItem onSelect={() => downloadEstimate("csv")}>
                  CSV
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>
      ) : null}
    </section>
  );
}

async function loadEstimateDocument(projectId: string) {
  const response = await fetch(
    `/api/v3/projects/${encodeURIComponent(projectId)}/estimate`,
    {
      method: "GET",
      headers: { Accept: "application/json" },
      credentials: "same-origin",
      cache: "no-store",
    },
  );
  if (!response.ok) throw new Error(await readResponseError(response));
  const parsed = kolibriGenerativeUIComponentSchemas.EstimateEditor.safeParse(
    await response.json(),
  );
  if (!parsed.success) {
    throw new Error("Сервер вернул смету неизвестного формата.");
  }
  return parsed.data;
}

async function loadProjectContextSummary(
  projectId: string,
): Promise<ProjectContextSummary> {
  const response = await fetch(
    `/api/v3/projects/${encodeURIComponent(projectId)}/context`,
    {
      method: "GET",
      headers: { Accept: "application/json" },
      credentials: "same-origin",
      cache: "no-store",
    },
  );
  if (!response.ok) throw new Error(await readResponseError(response));
  const value: unknown = await response.json();
  if (typeof value !== "object" || value === null) {
    throw new Error("Сервер вернул неизвестный контекст проекта.");
  }
  const record = value as Record<string, unknown>;
  const project = record.project;
  const object = record.object;
  const parties = Array.isArray(record.parties) ? record.parties : [];
  if (typeof project !== "object" || project === null) {
    throw new Error("В контексте отсутствует проект.");
  }
  const projectName = (project as Record<string, unknown>).name;
  if (typeof projectName !== "string" || projectName.trim() === "") {
    throw new Error("В контексте отсутствует название проекта.");
  }
  const partySummary = (
    role: "client" | "contractor",
  ): ProjectPartySummary | null => {
    const party = parties.find(
      (candidate) =>
        typeof candidate === "object" &&
        candidate !== null &&
        (candidate as Record<string, unknown>).role === role &&
        (candidate as Record<string, unknown>).isPrimary === true,
    );
    if (typeof party !== "object" || party === null) return null;
    const value = party as Record<string, unknown>;
    if (
      typeof value.id !== "string" ||
      (value.entityType !== "person" && value.entityType !== "organization") ||
      typeof value.displayName !== "string"
    ) {
      return null;
    }
    return {
      id: value.id,
      role,
      entityType: value.entityType,
      displayName: value.displayName,
      taxId: typeof value.taxId === "string" ? value.taxId : null,
      registrationCode:
        typeof value.registrationCode === "string"
          ? value.registrationCode
          : null,
    };
  };
  const objectName =
    typeof object === "object" &&
    object !== null &&
    typeof (object as Record<string, unknown>).name === "string"
      ? String((object as Record<string, unknown>).name)
      : null;
  return {
    projectName,
    objectName,
    client: partySummary("client"),
    contractor: partySummary("contractor"),
  };
}

async function saveProjectParty(
  projectId: string,
  role: "client" | "contractor",
  payload: {
    displayName: string;
    entityType: "person" | "organization";
    taxId: string | null;
    registrationCode: string | null;
  },
) {
  const response = await fetch(
    `/api/v3/projects/${encodeURIComponent(projectId)}/parties/${role}`,
    {
      method: "PUT",
      headers: withCsrfHeader({
        Accept: "application/json",
        "Content-Type": "application/json",
      }),
      credentials: "same-origin",
      cache: "no-store",
      body: JSON.stringify(payload),
    },
  );
  if (!response.ok) throw new Error(await readResponseError(response));
}

async function copyEstimateForClient(
  projectId: string,
  idempotencyKey: string,
  payload: {
    projectName: string;
    objectName: string;
    client: {
      displayName: string;
      entityType: "person" | "organization";
      taxId: string | null;
      registrationCode: string | null;
    };
    retainSourceContractor: boolean;
  },
): Promise<EstimateCopyResult> {
  const response = await fetch(
    `/api/v3/projects/${encodeURIComponent(projectId)}/estimate/copies`,
    {
      method: "POST",
      headers: withCsrfHeader({
        Accept: "application/json",
        "Content-Type": "application/json",
        "Idempotency-Key": idempotencyKey,
      }),
      credentials: "same-origin",
      cache: "no-store",
      body: JSON.stringify(payload),
    },
  );
  if (!response.ok) throw new Error(await readResponseError(response));
  const value: unknown = await response.json();
  if (typeof value !== "object" || value === null) {
    throw new Error("Сервер вернул неизвестный результат копирования.");
  }
  const record = value as Record<string, unknown>;
  const project = record.project as Record<string, unknown> | undefined;
  const document = record.document as Record<string, unknown> | undefined;
  const lineage = record.lineage as Record<string, unknown> | undefined;
  if (
    !project ||
    !document ||
    !lineage ||
    typeof project.id !== "string" ||
    typeof project.name !== "string" ||
    typeof project.objectName !== "string" ||
    typeof project.threadId !== "string" ||
    typeof document.id !== "string" ||
    typeof document.version !== "number" ||
    typeof document.contentHash !== "string" ||
    typeof lineage.sourceProjectId !== "string" ||
    typeof lineage.sourceDocumentId !== "string" ||
    typeof lineage.sourceVersion !== "number" ||
    typeof lineage.sourceContentHash !== "string"
  ) {
    throw new Error("Сервер вернул неизвестный результат копирования.");
  }
  return {
    project: {
      id: project.id,
      name: project.name,
      objectName: project.objectName,
      threadId: project.threadId,
    },
    document: {
      id: document.id,
      version: document.version,
      contentHash: document.contentHash,
    },
    lineage: {
      sourceProjectId: lineage.sourceProjectId,
      sourceDocumentId: lineage.sourceDocumentId,
      sourceVersion: lineage.sourceVersion,
      sourceContentHash: lineage.sourceContentHash,
    },
  };
}

function optionalValue(value: string) {
  const normalized = value.trim();
  return normalized === "" ? null : normalized;
}

function PartyEditor({
  projectId,
  role,
  party,
  onSaved,
}: {
  projectId: string;
  role: "client" | "contractor";
  party: ProjectPartySummary | null;
  onSaved: () => Promise<void>;
}) {
  const [displayName, setDisplayName] = useState(party?.displayName ?? "");
  const [entityType, setEntityType] = useState<"person" | "organization">(
    party?.entityType ?? "organization",
  );
  const [taxId, setTaxId] = useState(party?.taxId ?? "");
  const [registrationCode, setRegistrationCode] = useState(
    party?.registrationCode ?? "",
  );
  const [saving, setSaving] = useState(false);
  const [statusText, setStatusText] = useState("");
  const label = role === "client" ? "Клиент" : "Подрядчик";

  useEffect(() => {
    setDisplayName(party?.displayName ?? "");
    setEntityType(party?.entityType ?? "organization");
    setTaxId(party?.taxId ?? "");
    setRegistrationCode(party?.registrationCode ?? "");
  }, [party]);

  return (
    <form
      className="rounded-xl border border-border bg-background p-3"
      onSubmit={(event) => {
        event.preventDefault();
        setSaving(true);
        setStatusText("");
        void saveProjectParty(projectId, role, {
          displayName: displayName.trim(),
          entityType,
          taxId: optionalValue(taxId),
          registrationCode:
            entityType === "organization"
              ? optionalValue(registrationCode)
              : null,
        })
          .then(onSaved)
          .then(() => setStatusText("Назначение сохранено"))
          .catch((reason: unknown) =>
            setStatusText(
              reason instanceof Error
                ? reason.message
                : "Не удалось сохранить участника.",
            ),
          )
          .finally(() => setSaving(false));
      }}
    >
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <p className="text-sm font-medium">{label}</p>
          <p className="text-xs text-muted-foreground">
            {party ? "Основной участник проекта" : "Пока не назначен"}
          </p>
        </div>
        {party ? (
          <CheckCircle2Icon
            aria-label="Назначен"
            className="size-4 text-emerald-600"
          />
        ) : null}
      </div>
      <div className="grid gap-2 sm:grid-cols-2">
        <label className="grid gap-1 text-xs text-muted-foreground sm:col-span-2">
          Имя или организация
          <Input
            required
            maxLength={240}
            value={displayName}
            onChange={(event) => setDisplayName(event.target.value)}
            placeholder={
              role === "client" ? "Например, ООО Заказчик" : "ООО Подрядчик"
            }
          />
        </label>
        <label className="grid gap-1 text-xs text-muted-foreground">
          Тип
          <select
            className="h-9 rounded-md border border-input bg-transparent px-3 text-sm outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
            value={entityType}
            onChange={(event) =>
              setEntityType(
                event.target.value === "person" ? "person" : "organization",
              )
            }
          >
            <option value="organization">Организация</option>
            <option value="person">Физлицо / ИП</option>
          </select>
        </label>
        <label className="grid gap-1 text-xs text-muted-foreground">
          ИНН, необязательно
          <Input
            inputMode="numeric"
            pattern="(?:[0-9]{10}|[0-9]{12})"
            value={taxId}
            onChange={(event) => setTaxId(event.target.value)}
            placeholder="10 или 12 цифр"
          />
        </label>
        {entityType === "organization" ? (
          <label className="grid gap-1 text-xs text-muted-foreground">
            КПП, необязательно
            <Input
              inputMode="numeric"
              pattern="[0-9]{9}"
              value={registrationCode}
              onChange={(event) => setRegistrationCode(event.target.value)}
              placeholder="9 цифр"
            />
          </label>
        ) : null}
      </div>
      <div className="mt-3 flex items-center gap-3">
        <Button type="submit" size="sm" disabled={saving}>
          {saving ? (
            <LoaderCircleIcon
              aria-hidden="true"
              className="size-4 animate-spin"
            />
          ) : null}
          {party ? "Обновить" : "Назначить"}
        </Button>
        {statusText ? (
          <p className="text-xs text-muted-foreground" role="status">
            {statusText}
          </p>
        ) : null}
      </div>
    </form>
  );
}

function ProjectPartiesPanel({
  projectId,
  context,
  onSaved,
}: {
  projectId: string;
  context: ProjectContextSummary;
  onSaved: () => Promise<void>;
}) {
  return (
    <div className="grid gap-3 md:grid-cols-2">
      <PartyEditor
        projectId={projectId}
        role="client"
        party={context.client}
        onSaved={onSaved}
      />
      <PartyEditor
        projectId={projectId}
        role="contractor"
        party={context.contractor}
        onSaved={onSaved}
      />
    </div>
  );
}

function EstimateCopyPanel({
  estimate,
  context,
}: {
  estimate: EstimateWidgetProps;
  context: ProjectContextSummary;
}) {
  const [projectName, setProjectName] = useState(
    `Копия — ${context.projectName}`,
  );
  const [objectName, setObjectName] = useState(
    context.objectName ?? "Объект уточняется",
  );
  const [clientName, setClientName] = useState("");
  const [clientType, setClientType] = useState<"person" | "organization">(
    "organization",
  );
  const [clientTaxId, setClientTaxId] = useState("");
  const [clientRegistrationCode, setClientRegistrationCode] = useState("");
  const [retainContractor, setRetainContractor] = useState(
    context.contractor !== null,
  );
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<EstimateCopyResult | null>(null);
  const idempotencyKey = useRef<string | null>(null);

  if (result) {
    return (
      <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-emerald-950">
        <div className="flex items-start gap-3">
          <CheckCircle2Icon
            aria-hidden="true"
            className="mt-0.5 size-5 shrink-0"
          />
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold">Создан отдельный проект</p>
            <p className="mt-1 text-sm">
              {result.project.name} · {result.project.objectName}
            </p>
            <p className="mt-1 text-xs opacity-75">
              Источник: версия {result.lineage.sourceVersion} текущей сметы.
              Копия получила собственный документ версии{" "}
              {result.document.version}.
            </p>
            <Button
              type="button"
              size="sm"
              className="mt-3"
              onClick={() =>
                openEstimateInWorkspace({
                  documentId: result.document.id,
                  projectId: result.project.id,
                  title: estimate.estimateTitle,
                  version: result.document.version,
                  projectName: result.project.name,
                })
              }
            >
              Открыть копию
            </Button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <form
      className="rounded-xl border border-border bg-background p-4"
      onSubmit={(event) => {
        event.preventDefault();
        setSubmitting(true);
        setError("");
        idempotencyKey.current ??=
          `estimate-copy-${crypto.randomUUID()}`;
        void copyEstimateForClient(
          estimate.projectId,
          idempotencyKey.current,
          {
            projectName: projectName.trim(),
            objectName: objectName.trim(),
            client: {
              displayName: clientName.trim(),
              entityType: clientType,
              taxId: optionalValue(clientTaxId),
              registrationCode:
                clientType === "organization"
                  ? optionalValue(clientRegistrationCode)
                  : null,
            },
            retainSourceContractor: retainContractor,
          },
        )
          .then((value) => {
            setResult(value);
            idempotencyKey.current = null;
            announceDocumentsChanged();
          })
          .catch((reason: unknown) =>
            setError(
              reason instanceof Error
                ? reason.message
                : "Не удалось повторить смету.",
            ),
          )
          .finally(() => setSubmitting(false));
      }}
    >
      <div className="mb-4">
        <p className="text-sm font-semibold">Повторить для другого клиента</p>
        <p className="mt-1 text-xs text-muted-foreground">
          Будет создан новый проект и новый документ. Исходная смета останется
          неизменной, а связь с её текущей версией сохранится.
        </p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="grid gap-1 text-xs text-muted-foreground">
          Новый проект
          <Input
            required
            maxLength={240}
            value={projectName}
            onChange={(event) => setProjectName(event.target.value)}
          />
        </label>
        <label className="grid gap-1 text-xs text-muted-foreground">
          Объект
          <Input
            required
            maxLength={240}
            value={objectName}
            onChange={(event) => setObjectName(event.target.value)}
          />
        </label>
        <label className="grid gap-1 text-xs text-muted-foreground sm:col-span-2">
          Новый клиент
          <Input
            required
            maxLength={240}
            value={clientName}
            onChange={(event) => setClientName(event.target.value)}
            placeholder="Имя или название организации"
          />
        </label>
        <label className="grid gap-1 text-xs text-muted-foreground">
          Тип клиента
          <select
            className="h-9 rounded-md border border-input bg-transparent px-3 text-sm outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
            value={clientType}
            onChange={(event) =>
              setClientType(
                event.target.value === "person" ? "person" : "organization",
              )
            }
          >
            <option value="organization">Организация</option>
            <option value="person">Физлицо / ИП</option>
          </select>
        </label>
        <label className="grid gap-1 text-xs text-muted-foreground">
          ИНН, необязательно
          <Input
            inputMode="numeric"
            pattern="(?:[0-9]{10}|[0-9]{12})"
            value={clientTaxId}
            onChange={(event) => setClientTaxId(event.target.value)}
            placeholder="10 или 12 цифр"
          />
        </label>
        {clientType === "organization" ? (
          <label className="grid gap-1 text-xs text-muted-foreground">
            КПП, необязательно
            <Input
              inputMode="numeric"
              pattern="[0-9]{9}"
              value={clientRegistrationCode}
              onChange={(event) =>
                setClientRegistrationCode(event.target.value)
              }
              placeholder="9 цифр"
            />
          </label>
        ) : null}
      </div>
      {context.contractor ? (
        <label className="mt-3 flex items-start gap-2 text-sm">
          <input
            type="checkbox"
            className="mt-0.5 size-4 rounded border-input"
            checked={retainContractor}
            onChange={(event) => setRetainContractor(event.target.checked)}
          />
          <span>
            Оставить подрядчика «{context.contractor.displayName}» в новом
            проекте
          </span>
        </label>
      ) : null}
      <div className="mt-4 flex items-center gap-3">
        <Button type="submit" size="sm" disabled={submitting}>
          {submitting ? (
            <LoaderCircleIcon
              aria-hidden="true"
              className="size-4 animate-spin"
            />
          ) : (
            <CopyIcon aria-hidden="true" className="size-4" />
          )}
          Создать отдельный проект
        </Button>
        {error ? (
          <p className="text-xs text-destructive" role="alert">
            {error}
          </p>
        ) : null}
      </div>
    </form>
  );
}

function downloadSavedEstimate(
  projectId: string,
  format: EstimateExportFormat,
) {
  const anchor = document.createElement("a");
  anchor.href = `/api/v3/projects/${encodeURIComponent(projectId)}/estimate/export/${format}`;
  anchor.download = "";
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
}

export function EstimateDocumentCard(initial: EstimateWidgetProps) {
  const currentCard = useAuiState((state) => {
    const latest = [...state.thread.messages]
      .reverse()
      .find((message) =>
        containsEstimateDocument(message.content, initial.documentId),
      );
    return latest?.id === state.message.id;
  });
  const [expanded, setExpanded] = useState(false);
  const [openedOnce, setOpenedOnce] = useState(false);
  const [activePanel, setActivePanel] = useState<
    "parties" | "copy" | null
  >(null);
  const [estimate, setEstimate] = useState(initial);
  const [projectContext, setProjectContext] =
    useState<ProjectContextSummary | null>(null);

  const refresh = useCallback(async () => {
    try {
      setEstimate(await loadEstimateDocument(initial.projectId));
    } catch {
      // The immutable tool snapshot remains visible while reconnecting.
    }
  }, [initial.projectId]);

  const refreshContext = useCallback(async () => {
    setProjectContext(await loadProjectContextSummary(initial.projectId));
  }, [initial.projectId]);

  useEffect(() => {
    void refresh();
    void refreshContext().catch(() => undefined);
    const handleChange = () => {
      void refresh();
      void refreshContext().catch(() => undefined);
    };
    window.addEventListener(KOLIBRI_DOCUMENTS_CHANGED_EVENT, handleChange);
    return () =>
      window.removeEventListener(KOLIBRI_DOCUMENTS_CHANGED_EVENT, handleChange);
  }, [refresh, refreshContext]);

  const toggleExpanded = () => {
    setExpanded((current) => {
      const next = !current;
      if (next) setOpenedOnce(true);
      return next;
    });
  };

  const openEditor = () => {
    if (window.matchMedia("(max-width: 959px)").matches) {
      openEstimateInWorkspace({
        documentId: estimate.documentId,
        projectId: estimate.projectId,
        projectName: projectContext?.projectName,
        title: estimate.estimateTitle,
        version: estimate.version,
      });
      return;
    }
    toggleExpanded();
  };

  if (!currentCard) return null;

  const cardSummary = (
    <>
      <span className="row-span-2 grid size-10 shrink-0 place-items-center rounded-xl bg-muted text-muted-foreground sm:row-auto">
        <FileSpreadsheetIcon aria-hidden="true" className="size-5" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-semibold">
          {estimate.estimateTitle}
        </span>
        {projectContext ? (
          <span className="mt-0.5 block truncate text-xs text-muted-foreground">
            {projectContext.projectName}
            {projectContext.objectName
              ? ` · ${projectContext.objectName}`
              : ""}
            {projectContext.client
              ? ` · клиент: ${projectContext.client.displayName}`
              : ""}
            {projectContext.contractor
              ? ` · подрядчик: ${projectContext.contractor.displayName}`
              : ""}
          </span>
        ) : null}
        <span className="mt-0.5 block text-xs text-muted-foreground">
          Документы → Сметы · {estimate.rows.length} поз. · версия{" "}
          {estimate.version}
        </span>
      </span>
      <span className="col-start-2 row-start-2 min-w-0 text-left sm:min-w-28 sm:text-right">
        <span className="block text-[11px] text-muted-foreground">
          Итого
        </span>
        <span className="block text-base font-semibold tabular-nums">
          {formatMoney(estimate.totals.total)}
        </span>
      </span>
      {!expanded ? (
        <ChevronDownIcon
          aria-hidden="true"
          className="col-start-3 row-span-2 row-start-1 size-4 shrink-0 self-center text-muted-foreground sm:col-auto sm:row-auto"
        />
      ) : null}
    </>
  );

  return (
    <section
      className="overflow-hidden rounded-2xl border border-border bg-card"
      aria-label="Смета проекта"
    >
      <div className="flex min-w-0 items-stretch">
        {expanded ? (
          <div className="grid min-w-0 flex-1 grid-cols-[2.5rem_minmax(0,1fr)_auto] gap-x-3 gap-y-1.5 p-4 text-left sm:flex sm:items-center sm:gap-3">
            {cardSummary}
          </div>
        ) : (
          <button
            type="button"
            className="grid min-w-0 flex-1 grid-cols-[2.5rem_minmax(0,1fr)_auto] gap-x-3 gap-y-1.5 p-4 text-left transition-colors hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset sm:flex sm:items-center sm:gap-3"
            aria-expanded="false"
            aria-label={`Открыть смету «${estimate.estimateTitle}» для редактирования`}
            onClick={openEditor}
          >
            {cardSummary}
          </button>
        )}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              type="button"
              size="icon"
              variant="ghost"
              className="my-auto mr-2 shrink-0"
              aria-label="Ещё действия со сметой"
            >
              <MoreHorizontalIcon aria-hidden="true" className="size-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-52">
            <DropdownMenuItem
              onSelect={() =>
                setActivePanel((current) =>
                  current === "parties" ? null : "parties",
                )
              }
            >
              <UsersIcon aria-hidden="true" />
              Участники
            </DropdownMenuItem>
            <DropdownMenuItem
              disabled={!projectContext}
              onSelect={() =>
                setActivePanel((current) =>
                  current === "copy" ? null : "copy",
                )
              }
            >
              <CopyIcon aria-hidden="true" />
              Повторить для клиента
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuLabel className="text-xs">Скачать</DropdownMenuLabel>
            <DropdownMenuItem
              onSelect={() =>
                downloadSavedEstimate(estimate.projectId, "pdf")
              }
            >
              PDF
            </DropdownMenuItem>
            <DropdownMenuItem
              onSelect={() =>
                downloadSavedEstimate(estimate.projectId, "xlsx")
              }
            >
              Excel
            </DropdownMenuItem>
            <DropdownMenuItem
              onSelect={() =>
                downloadSavedEstimate(estimate.projectId, "docx")
              }
            >
              Word
            </DropdownMenuItem>
            <DropdownMenuItem
              onSelect={() =>
                downloadSavedEstimate(estimate.projectId, "csv")
              }
            >
              CSV
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      {activePanel && projectContext ? (
        <div className="border-t border-border bg-muted/20 p-4">
          {activePanel === "parties" ? (
            <ProjectPartiesPanel
              projectId={estimate.projectId}
              context={projectContext}
              onSaved={refreshContext}
            />
          ) : (
            <EstimateCopyPanel
              key={`${estimate.documentId}:${estimate.version}`}
              estimate={estimate}
              context={projectContext}
            />
          )}
        </div>
      ) : null}

      {openedOnce ? (
        <div hidden={!expanded}>
          <EstimateEditorWidget {...estimate} presentation="inline" />
          <button
            type="button"
            className="text-muted-foreground hover:bg-muted/50 hover:text-foreground focus-visible:ring-ring flex h-10 w-full items-center justify-center border-t border-border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset"
            aria-expanded="true"
            aria-label={`Свернуть смету «${estimate.estimateTitle}»`}
            onClick={toggleExpanded}
          >
            <ChevronDownIcon
              aria-hidden="true"
              className="size-4 rotate-180"
            />
          </button>
        </div>
      ) : null}
    </section>
  );
}

export function EstimateDocumentSurface({
  projectId,
}: {
  projectId: string;
}) {
  const [estimate, setEstimate] = useState<EstimateWidgetProps | null>(null);
  const [projectContext, setProjectContext] =
    useState<ProjectContextSummary | null>(null);
  const [activePanel, setActivePanel] = useState<
    "parties" | "copy" | null
  >(null);
  const [error, setError] = useState("");

  const refreshContext = useCallback(async () => {
    setProjectContext(await loadProjectContextSummary(projectId));
  }, [projectId]);

  useEffect(() => {
    let active = true;
    void loadEstimateDocument(projectId)
      .then((value) => {
        if (active) setEstimate(value);
      })
      .catch((reason: unknown) => {
        if (active) {
          setError(
            reason instanceof Error
              ? reason.message
              : "Не удалось открыть смету.",
          );
        }
      });
    void refreshContext().catch(() => undefined);
    return () => {
      active = false;
    };
  }, [projectId, refreshContext]);

  if (error) {
    return (
      <div className="text-destructive flex min-h-48 items-center justify-center p-6 text-sm">
        {error}
      </div>
    );
  }
  if (!estimate) {
    return (
      <div className="text-muted-foreground flex min-h-48 items-center justify-center gap-2 p-6 text-sm">
        <LoaderCircleIcon aria-hidden="true" className="size-4 animate-spin" />
        Загружаю сохранённую смету…
      </div>
    );
  }
  return (
    <div data-slot="estimate-document-surface" className="min-w-0 space-y-3">
      {projectContext ? (
        <section
          data-slot="estimate-project-context"
          className="overflow-hidden rounded-xl border border-border bg-card"
        >
          <div
            data-slot="estimate-project-context-toolbar"
            className="flex flex-wrap items-center gap-3 px-4 py-3"
          >
            <div
              data-slot="estimate-project-context-summary"
              className="min-w-0 flex-1"
            >
              <p className="truncate text-sm font-medium">
                {projectContext.projectName}
              </p>
              <p className="mt-0.5 truncate text-xs text-muted-foreground">
                {projectContext.objectName ?? "Объект уточняется"}
                {projectContext.client
                  ? ` · клиент: ${projectContext.client.displayName}`
                  : " · клиент не назначен"}
                {projectContext.contractor
                  ? ` · подрядчик: ${projectContext.contractor.displayName}`
                  : ""}
              </p>
            </div>
            <Button
              data-slot="estimate-project-context-action"
              type="button"
              size="sm"
              variant={activePanel === "parties" ? "secondary" : "outline"}
              aria-expanded={activePanel === "parties"}
              onClick={() =>
                setActivePanel((current) =>
                  current === "parties" ? null : "parties",
                )
              }
            >
              <UsersIcon aria-hidden="true" className="size-4" />
              Участники
            </Button>
            <Button
              data-slot="estimate-project-context-action"
              type="button"
              size="sm"
              variant={activePanel === "copy" ? "secondary" : "outline"}
              aria-expanded={activePanel === "copy"}
              onClick={() =>
                setActivePanel((current) =>
                  current === "copy" ? null : "copy",
                )
              }
            >
              <CopyIcon aria-hidden="true" className="size-4" />
              Повторить
            </Button>
          </div>
          {activePanel ? (
            <div className="border-t border-border bg-muted/20 p-4">
              {activePanel === "parties" ? (
                <ProjectPartiesPanel
                  projectId={estimate.projectId}
                  context={projectContext}
                  onSaved={refreshContext}
                />
              ) : (
                <EstimateCopyPanel
                  key={`${estimate.documentId}:${estimate.version}:canvas`}
                  estimate={estimate}
                  context={projectContext}
                />
              )}
            </div>
          ) : null}
        </section>
      ) : null}
      <EstimateEditorWidget {...estimate} presentation="canvas" />
    </div>
  );
}
