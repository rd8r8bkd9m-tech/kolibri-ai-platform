"use client";

import { useAssistantContext } from "@assistant-ui/react";
import {
  ArrowLeft,
  Building2,
  Database,
  Hammer,
  LayoutTemplate,
  LibraryBig,
  LoaderCircle,
  LockKeyhole,
  Package,
  Percent,
  RefreshCw,
  Ruler,
  Search,
  TriangleAlert,
  type LucideIcon,
} from "lucide-react";
import {
  useCallback,
  useEffect,
  useId,
  useMemo,
  useState,
} from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { KOLIBRI_DOCUMENTS_CHANGED_EVENT } from "@/lib/workspace-events";
import { cn } from "@/lib/utils";

const REFERENCE_CATEGORIES = [
  { id: "works", label: "Работы", icon: Hammer },
  { id: "materials", label: "Материалы", icon: Package },
  { id: "units", label: "Единицы", icon: Ruler },
  {
    id: "indices",
    label: "Индексы и коэффициенты",
    icon: Percent,
  },
  { id: "counterparties", label: "Контрагенты", icon: Building2 },
  { id: "templates", label: "Шаблоны", icon: LayoutTemplate },
] as const satisfies ReadonlyArray<{
  id: string;
  label: string;
  icon: LucideIcon;
}>;

type ReferenceCategoryId = (typeof REFERENCE_CATEGORIES)[number]["id"];
type CatalogState = "loading" | "ready" | "error";
type PriceEntryKind = "work" | "material" | "equipment" | "service";

type PersonalPriceEntry = {
  itemKey: string;
  kind: PriceEntryKind;
  description: string;
  region: string;
  unit: string;
  latestPrice: string;
  medianPrice: string;
  lowerQuartile: string;
  upperQuartile: string;
  sampleSize: number;
  latestSource: string;
  latestLifecycle: string;
  latestObservedAt: string;
};

type PersonalPriceCatalog = {
  scope: "personal";
  aggregation: {
    method: "median_iqr";
    crossTenantEnabled: false;
  };
  entries: PersonalPriceEntry[];
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function parsePersonalPriceCatalog(value: unknown): PersonalPriceCatalog {
  if (!isRecord(value) || value.scope !== "personal") {
    throw new Error("Price catalog has an incompatible shape.");
  }
  const aggregation = value.aggregation;
  if (
    !isRecord(aggregation) ||
    aggregation.method !== "median_iqr" ||
    aggregation.crossTenantEnabled !== false ||
    !Array.isArray(value.entries)
  ) {
    throw new Error("Price catalog aggregation has an incompatible shape.");
  }
  const entries = value.entries.map((raw): PersonalPriceEntry => {
    if (!isRecord(raw)) {
      throw new Error("Price catalog entry has an incompatible shape.");
    }
    const kind = raw.kind;
    if (
      kind !== "work" &&
      kind !== "material" &&
      kind !== "equipment" &&
      kind !== "service"
    ) {
      throw new Error("Price catalog entry kind is invalid.");
    }
    const stringFields = [
      "itemKey",
      "description",
      "region",
      "unit",
      "latestPrice",
      "medianPrice",
      "lowerQuartile",
      "upperQuartile",
      "latestSource",
      "latestLifecycle",
      "latestObservedAt",
    ] as const;
    for (const field of stringFields) {
      if (typeof raw[field] !== "string") {
        throw new Error(`Price catalog entry ${field} is invalid.`);
      }
    }
    if (
      typeof raw.sampleSize !== "number" ||
      !Number.isInteger(raw.sampleSize) ||
      raw.sampleSize < 1
    ) {
      throw new Error("Price catalog sample size is invalid.");
    }
    return {
      itemKey: raw.itemKey as string,
      kind,
      description: raw.description as string,
      region: raw.region as string,
      unit: raw.unit as string,
      latestPrice: raw.latestPrice as string,
      medianPrice: raw.medianPrice as string,
      lowerQuartile: raw.lowerQuartile as string,
      upperQuartile: raw.upperQuartile as string,
      sampleSize: raw.sampleSize,
      latestSource: raw.latestSource as string,
      latestLifecycle: raw.latestLifecycle as string,
      latestObservedAt: raw.latestObservedAt as string,
    };
  });
  return {
    scope: "personal",
    aggregation: {
      method: "median_iqr",
      crossTenantEnabled: false,
    },
    entries,
  };
}

function formatMoney(value: string) {
  const amount = Number(value);
  if (!Number.isFinite(amount)) return value;
  return new Intl.NumberFormat("ru-RU", {
    style: "currency",
    currency: "RUB",
    maximumFractionDigits: 2,
  }).format(amount);
}

function sourceLabel(source: string) {
  if (source === "contract_price") return "Договор";
  if (source === "customer_approved") return "Принято клиентом";
  if (source === "supplier_offer") return "Предложение";
  if (source === "official_reference") return "Официальный ориентир";
  if (source === "user_edit") return "Личная цена";
  if (source === "ai_preliminary") return "Предварительно AI";
  return source;
}

function categoryEntries(
  entries: readonly PersonalPriceEntry[],
  category: ReferenceCategoryId,
) {
  if (category === "materials") {
    return entries.filter((entry) => entry.kind === "material");
  }
  if (category === "works") {
    return entries.filter((entry) => entry.kind !== "material");
  }
  return [];
}

export function ReferenceCatalog({ onBack }: { onBack?: () => void }) {
  const titleId = useId();
  const descriptionId = useId();
  const [activeCategory, setActiveCategory] =
    useState<ReferenceCategoryId>("works");
  const [catalog, setCatalog] = useState<PersonalPriceCatalog | null>(null);
  const [catalogState, setCatalogState] = useState<CatalogState>("loading");
  const [query, setQuery] = useState("");

  const activeCategoryDefinition =
    REFERENCE_CATEGORIES.find(({ id }) => id === activeCategory) ??
    REFERENCE_CATEGORIES[0];

  const loadCatalog = useCallback(async () => {
    setCatalogState("loading");
    try {
      const response = await fetch("/api/v3/pricing/catalog?limit=100", {
        method: "GET",
        headers: { Accept: "application/json" },
        credentials: "same-origin",
        cache: "no-store",
      });
      if (!response.ok) {
        throw new Error(`Price catalog returned HTTP ${response.status}.`);
      }
      setCatalog(parsePersonalPriceCatalog(await response.json()));
      setCatalogState("ready");
    } catch {
      setCatalogState("error");
    }
  }, []);

  useEffect(() => {
    void loadCatalog();
    const refresh = () => void loadCatalog();
    window.addEventListener(KOLIBRI_DOCUMENTS_CHANGED_EVENT, refresh);
    return () =>
      window.removeEventListener(KOLIBRI_DOCUMENTS_CHANGED_EVENT, refresh);
  }, [loadCatalog]);

  const selectedEntries = useMemo(() => {
    const entries = categoryEntries(catalog?.entries ?? [], activeCategory);
    const normalizedQuery = query.trim().toLocaleLowerCase("ru-RU");
    if (!normalizedQuery) return entries;
    return entries.filter((entry) =>
      [entry.description, entry.region, entry.unit]
        .join(" ")
        .toLocaleLowerCase("ru-RU")
        .includes(normalizedQuery),
    );
  }, [activeCategory, catalog?.entries, query]);

  const units = useMemo(() => {
    const counts = new Map<string, number>();
    for (const entry of catalog?.entries ?? []) {
      counts.set(entry.unit, (counts.get(entry.unit) ?? 0) + 1);
    }
    return [...counts.entries()].sort(([left], [right]) =>
      left.localeCompare(right, "ru"),
    );
  }, [catalog?.entries]);

  useAssistantContext({
    getContext: () =>
      [
        "Контекст личного справочника цен Kolibri. Данные принадлежат текущему tenant и пользователю. Это личная история наблюдений, а не общий рыночный индекс. Межтенантное агрегирование выключено. Официальный ориентир, AI-оценка, личная правка, предложение, принятая клиентом цена и договор имеют разную доказательную силу. Этот контекст read-only и не даёт полномочий изменять цены.",
        JSON.stringify({
          surface: "reference_catalog",
          access: "read_only",
          data_status: catalogState,
          scope: "tenant_user_private",
          cross_tenant_aggregation: false,
          category: {
            id: activeCategoryDefinition.id,
            label: activeCategoryDefinition.label,
          },
          visible_entries: selectedEntries.slice(0, 25),
        }),
      ].join("\n"),
  });

  const hasPriceData =
    activeCategory === "works" || activeCategory === "materials";
  const knownCount =
    activeCategory === "units"
      ? units.length
      : hasPriceData
        ? categoryEntries(catalog?.entries ?? [], activeCategory).length
        : null;

  return (
    <TooltipProvider delayDuration={300}>
      <section
        className="bg-background @container flex min-h-0 flex-1 flex-col overflow-hidden"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
      >
        <header className="border-border/80 flex min-h-14 shrink-0 items-center gap-2 border-b px-2.5 py-2">
          {onBack ? (
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  className="size-11 rounded-lg @min-[700px]:size-8"
                  onClick={onBack}
                  aria-label="Вернуться к рабочему пространству"
                >
                  <ArrowLeft aria-hidden="true" />
                </Button>
              </TooltipTrigger>
              <TooltipContent side="bottom" sideOffset={6}>
                Назад к рабочему пространству
              </TooltipContent>
            </Tooltip>
          ) : null}

          <LibraryBig
            className="text-muted-foreground ml-0.5 size-4 shrink-0"
            aria-hidden="true"
          />
          <div className="min-w-0 flex-1">
            <h2 id={titleId} className="truncate text-sm font-semibold">
              Справочники
            </h2>
            <p className="text-muted-foreground truncate text-[10px] @min-[520px]:text-[11px]">
              Личная история цен и проектные каталоги
            </p>
          </div>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                onClick={() => void loadCatalog()}
                disabled={catalogState === "loading"}
                aria-label="Обновить личный справочник цен"
              >
                <RefreshCw
                  className={cn(
                    "size-4",
                    catalogState === "loading" && "animate-spin",
                  )}
                  aria-hidden="true"
                />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="bottom">Обновить</TooltipContent>
          </Tooltip>
        </header>

        <div
          id={descriptionId}
          role="note"
          className="border-border/80 bg-muted/15 flex shrink-0 flex-wrap items-start gap-x-4 gap-y-2 border-b px-3 py-2.5 @min-[620px]:items-center"
        >
          <div className="flex min-w-0 flex-1 items-start gap-2">
            <Database
              className="text-muted-foreground mt-0.5 size-3.5 shrink-0"
              aria-hidden="true"
            />
            <p className="text-muted-foreground text-[10px] leading-relaxed @min-[520px]:text-[11px]">
              <span className="text-foreground font-medium">
                Личный справочник цен.
              </span>{" "}
              Здесь сохраняются AI-черновики, официальные ориентиры,
              предложения и ваши изменения — раздельно и с историей.
            </p>
          </div>
          <span className="text-muted-foreground flex shrink-0 items-center gap-1.5 text-[10px]">
            <LockKeyhole className="size-3" aria-hidden="true" />
            Только ваши данные
          </span>
        </div>

        <nav
          className="border-border/80 shrink-0 overflow-x-auto border-b px-2 py-2 @min-[700px]:hidden"
          aria-label="Разделы справочника"
        >
          <div className="flex min-w-max gap-1">
            {REFERENCE_CATEGORIES.map(({ id, label }) => (
              <Button
                key={id}
                type="button"
                size="sm"
                variant={activeCategory === id ? "secondary" : "ghost"}
                className="min-h-11"
                onClick={() => setActiveCategory(id)}
                aria-pressed={activeCategory === id}
              >
                {label}
              </Button>
            ))}
          </div>
        </nav>

        <div className="grid min-h-0 flex-1 grid-cols-1 @min-[700px]:grid-cols-[204px_minmax(0,1fr)]">
          <aside className="border-border/80 bg-muted/10 hidden min-h-0 flex-col border-r p-2.5 @min-[700px]:flex">
            <nav aria-label="Разделы справочника">
              <p className="text-muted-foreground mb-2 px-2 text-[10px] font-semibold tracking-wide uppercase">
                Категории
              </p>
              <ul className="space-y-0.5">
                {REFERENCE_CATEGORIES.map(
                  ({ id, label, icon: CategoryIcon }) => (
                    <li key={id}>
                      <button
                        type="button"
                        onClick={() => setActiveCategory(id)}
                        aria-current={
                          activeCategory === id ? "page" : undefined
                        }
                        className={cn(
                          "focus-visible:ring-ring flex min-h-9 w-full items-center gap-2 rounded-lg px-2 text-left text-xs outline-none focus-visible:ring-2",
                          activeCategory === id
                            ? "bg-muted text-foreground font-medium"
                            : "text-muted-foreground hover:bg-muted/60 hover:text-foreground",
                        )}
                      >
                        <CategoryIcon
                          className="size-3.5 shrink-0"
                          aria-hidden="true"
                        />
                        <span className="min-w-0 flex-1 leading-tight">
                          {label}
                        </span>
                      </button>
                    </li>
                  ),
                )}
              </ul>
            </nav>
          </aside>

          <div className="flex min-h-0 min-w-0 flex-col">
            <div className="border-border/80 flex shrink-0 flex-wrap items-center gap-2 border-b px-3 py-2.5">
              <div className="min-w-0 flex-1">
                <h3 className="truncate text-xs font-semibold">
                  {activeCategoryDefinition.label}
                </h3>
                <p className="text-muted-foreground mt-0.5 text-[10px]">
                  {knownCount === null
                    ? "Источник раздела ещё не подключён"
                    : `${knownCount} ${knownCount === 1 ? "позиция" : "позиций"}`}
                </p>
              </div>
              {hasPriceData ? (
                <label className="relative min-w-44 flex-1 @min-[700px]:max-w-72">
                  <Search
                    className="text-muted-foreground pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2"
                    aria-hidden="true"
                  />
                  <span className="sr-only">Поиск по личному справочнику</span>
                  <Input
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                    placeholder="Работа, материал или регион"
                    className="h-8 pl-8 text-xs"
                  />
                </label>
              ) : null}
            </div>

            {catalogState === "loading" && !catalog ? (
              <div className="text-muted-foreground flex min-h-64 flex-1 flex-col items-center justify-center px-5 text-center">
                <LoaderCircle className="mb-3 size-5 animate-spin" aria-hidden="true" />
                <p className="text-foreground text-xs font-medium">
                  Загружаю личный справочник
                </p>
              </div>
            ) : catalogState === "error" && !catalog ? (
              <div
                className="text-muted-foreground flex min-h-64 flex-1 flex-col items-center justify-center px-5 text-center"
                role="alert"
              >
                <TriangleAlert className="mb-3 size-5" aria-hidden="true" />
                <p className="text-foreground text-xs font-medium">
                  Не удалось загрузить справочник
                </p>
                <p className="mt-1 max-w-sm text-[10px] leading-relaxed">
                  Данные не подменены пустым результатом. Проверьте соединение
                  и повторите загрузку.
                </p>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  className="mt-3"
                  onClick={() => void loadCatalog()}
                >
                  Повторить
                </Button>
              </div>
            ) : activeCategory === "units" ? (
              units.length > 0 ? (
                <div className="min-h-0 flex-1 overflow-auto">
                  <table className="w-full border-collapse text-left text-xs">
                    <caption className="sr-only">
                      Единицы личного справочника цен
                    </caption>
                    <thead className="bg-background sticky top-0">
                      <tr className="border-border/80 text-muted-foreground border-b">
                        <th className="px-3 py-2.5 font-medium">Единица</th>
                        <th className="px-3 py-2.5 text-right font-medium">
                          Позиций
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {units.map(([unit, count]) => (
                        <tr key={unit} className="border-border/60 border-b">
                          <td className="px-3 py-2.5 font-medium">{unit}</td>
                          <td className="px-3 py-2.5 text-right tabular-nums">
                            {count}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <EmptyCatalogState
                  title="Единицы появятся вместе с ценами"
                  description="Создайте смету или прикрепите предложение к её строке."
                />
              )
            ) : hasPriceData ? (
              selectedEntries.length > 0 ? (
                <div className="min-h-0 flex-1 overflow-auto">
                  <table className="w-full min-w-[780px] border-collapse text-left text-xs">
                    <caption className="sr-only">
                      Личный справочник цен: {activeCategoryDefinition.label}
                    </caption>
                    <thead className="bg-background sticky top-0">
                      <tr className="border-border/80 text-muted-foreground border-b">
                        <th className="min-w-60 px-3 py-2.5 font-medium">
                          Наименование
                        </th>
                        <th className="px-3 py-2.5 font-medium">Регион</th>
                        <th className="px-3 py-2.5 font-medium">Ед.</th>
                        <th className="px-3 py-2.5 text-right font-medium">
                          Последняя
                        </th>
                        <th className="px-3 py-2.5 text-right font-medium">
                          Личная медиана
                        </th>
                        <th className="px-3 py-2.5 font-medium">Источник</th>
                      </tr>
                    </thead>
                    <tbody>
                      {selectedEntries.map((entry) => (
                        <tr
                          key={`${entry.itemKey}:${entry.region}`}
                          className="border-border/60 border-b align-top"
                        >
                          <td className="px-3 py-2.5">
                            <p className="text-foreground font-medium">
                              {entry.description}
                            </p>
                            <p className="text-muted-foreground mt-0.5 text-[10px]">
                              {entry.sampleSize} наблюдений · диапазон{" "}
                              {formatMoney(entry.lowerQuartile)}–
                              {formatMoney(entry.upperQuartile)}
                            </p>
                          </td>
                          <td className="px-3 py-2.5">{entry.region}</td>
                          <td className="px-3 py-2.5">{entry.unit}</td>
                          <td className="px-3 py-2.5 text-right font-medium tabular-nums">
                            {formatMoney(entry.latestPrice)}
                          </td>
                          <td className="px-3 py-2.5 text-right tabular-nums">
                            {formatMoney(entry.medianPrice)}
                          </td>
                          <td className="px-3 py-2.5">
                            {sourceLabel(entry.latestSource)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <EmptyCatalogState
                  title={query ? "Ничего не найдено" : "Личных цен пока нет"}
                  description={
                    query
                      ? "Измените запрос или выберите другой раздел."
                      : "Цены появятся после создания и редактирования сметы или прикрепления источника."
                  }
                />
              )
            ) : (
              <EmptyCatalogState
                title="Источник раздела ещё не подключён"
                description={`Раздел «${activeCategoryDefinition.label}» будет подключён отдельным проверяемым источником.`}
              />
            )}
          </div>
        </div>
      </section>
    </TooltipProvider>
  );
}

function EmptyCatalogState({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <div className="text-muted-foreground flex min-h-64 flex-1 flex-col items-center justify-center px-5 text-center">
      <Database className="mb-3 size-5" aria-hidden="true" />
      <p className="text-foreground text-xs font-medium">{title}</p>
      <p className="mt-1 max-w-sm text-[10px] leading-relaxed">
        {description}
      </p>
    </div>
  );
}
