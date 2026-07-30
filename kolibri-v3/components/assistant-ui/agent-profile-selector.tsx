"use client";

import {
  ModelSelector,
  type ModelOption,
  type ModelSelectorEffortOption,
} from "@/components/assistant-ui/model-selector";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useIdentity } from "@/lib/identity/provider";
import type {
  CatalogModel,
  ServiceTierOption,
} from "@/lib/models/client";
import { useModelCatalog } from "@/lib/models/provider";
import {
  useDeveloperAgentMode,
  type DeveloperAccessMode,
} from "@/lib/product-chat/developer-agent-mode";
import { openModelSettings } from "@/lib/workspace-events";
import { useAuiState } from "@assistant-ui/react";
import {
  ChevronDownIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  LoaderCircleIcon,
  Settings2Icon,
  ShieldAlertIcon,
  ShieldCheckIcon,
  ZapIcon,
} from "lucide-react";
import {
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
  type FC,
} from "react";

const MOBILE_SELECTOR_QUERY = "(max-width: 959px)";

function subscribeMobileSelector(listener: () => void) {
  const media = window.matchMedia(MOBILE_SELECTOR_QUERY);
  media.addEventListener("change", listener);
  return () => media.removeEventListener("change", listener);
}

function mobileSelectorSnapshot() {
  return window.matchMedia(MOBILE_SELECTOR_QUERY).matches;
}

function serverMobileSelectorSnapshot() {
  return false;
}

const EFFORT_NAMES: Readonly<Record<string, string>> = {
  low: "Лёгкий",
  medium: "Средний",
  high: "Высокий",
  xhigh: "Очень высокий",
  max: "Макс.",
  ultra: "Ультра",
};

const EFFORT_DESCRIPTIONS: Readonly<Record<string, string>> = {
  low: "Быстрые ответы для простых задач",
  medium: "Баланс скорости и качества",
  high: "Больше времени на сложную задачу",
  xhigh: "Глубокий анализ и проверка решения",
  max: "Максимальная глубина рассуждений",
  ultra: "Быстрее расходует лимит использования",
};

const FALLBACK_MODELS: readonly CatalogModel[] = [
  {
    id: "auto",
    profile: "auto",
    displayName: "Авто",
    description: "Kolibri выберет доступную модель для задачи.",
    available: true,
    supportedReasoningEfforts: [],
    serviceTiers: [],
    defaultReasoningEffort: null,
    isDefault: true,
    upgrade: null,
  },
  {
    id: "mimo-code",
    profile: "mimo-code",
    displayName: "MiMo Code",
    description: "Модель Token Plan.",
    available: false,
    supportedReasoningEfforts: [],
    serviceTiers: [],
    defaultReasoningEffort: null,
    isDefault: false,
    upgrade: null,
  },
];

type MobilePage = "root" | "model" | "effort" | "speed";

function compactModelName(name: string) {
  return name.replace(/^GPT-/i, "");
}

function effortOptions(
  model: CatalogModel,
): readonly ModelSelectorEffortOption[] | undefined {
  if (model.supportedReasoningEfforts.length === 0) return undefined;
  return model.supportedReasoningEfforts.map((effort) => ({
    id: effort.id,
    name: EFFORT_NAMES[effort.id] ?? effort.id,
  }));
}

function toModelOption(model: CatalogModel): ModelOption {
  return {
    id: model.id,
    name: compactModelName(model.displayName),
    description: model.available
      ? model.description
      : `${model.description} Сначала подключите провайдера.`,
    disabled: !model.available,
    keywords: [
      model.profile,
      model.id,
      model.profile === "codex-cli" ? "codex openai" : "",
    ],
    efforts: effortOptions(model),
  };
}

function effectiveModelId(
  models: readonly CatalogModel[],
  user: NonNullable<ReturnType<typeof useIdentity>["user"]>,
  configuredCodexModel: string | null,
) {
  if (user.preferredAgentProfile === "auto") return "auto";
  if (user.preferredAgentProfile === "mimo-code") return "mimo-code";
  return (
    user.preferredModel ??
    configuredCodexModel ??
    models.find(
      (model) => model.profile === "codex-cli" && model.isDefault,
    )?.id ??
    models.find((model) => model.profile === "codex-cli")?.id
  );
}

function serviceTierName(tier: ServiceTierOption | undefined) {
  if (!tier) return "Стандартный";
  if (tier.id === "priority") return "Быстрый";
  return tier.name;
}

function keepMenuOpen(event: Event) {
  event.preventDefault();
}

type SelectorMenuProps = {
  models: readonly CatalogModel[];
  selectedModelId: string | undefined;
  selectedModel: CatalogModel | undefined;
  selectedEffort: string | undefined;
  selectedServiceTier: string | null;
  disabled: boolean;
  saving: boolean;
  onModelSelect: (id: string) => void;
  onEffortSelect: (id: string) => void;
  onServiceTierSelect: (id: string | null) => void;
};

function ModelItems({
  models,
  selectedModelId,
  disabled,
  onModelSelect,
}: Pick<
  SelectorMenuProps,
  "models" | "selectedModelId" | "disabled" | "onModelSelect"
>) {
  return (
    <DropdownMenuRadioGroup value={selectedModelId ?? ""}>
      {models.map((model) => (
        <DropdownMenuRadioItem
          key={model.id}
          value={model.id}
          disabled={disabled || !model.available}
          onSelect={(event) => {
            keepMenuOpen(event);
            onModelSelect(model.id);
          }}
          className="min-h-11 gap-3 px-3 py-2 text-[15px]"
        >
          <span className="min-w-0 flex-1 truncate">
            {compactModelName(model.displayName)}
          </span>
          {!model.available ? (
            <span className="text-muted-foreground shrink-0 text-xs">
              Не подключено
            </span>
          ) : null}
        </DropdownMenuRadioItem>
      ))}
    </DropdownMenuRadioGroup>
  );
}

function EffortItems({
  selectedModel,
  selectedEffort,
  disabled,
  onEffortSelect,
}: Pick<
  SelectorMenuProps,
  "selectedModel" | "selectedEffort" | "disabled" | "onEffortSelect"
>) {
  const efforts = selectedModel?.supportedReasoningEfforts ?? [];
  return (
    <>
      <DropdownMenuLabel className="text-muted-foreground px-3 pt-2 pb-1 text-sm font-normal">
        Усилия
      </DropdownMenuLabel>
      {efforts.length > 0 ? (
        <DropdownMenuRadioGroup value={selectedEffort ?? ""}>
          {efforts.map((effort) => (
            <DropdownMenuRadioItem
              key={effort.id}
              value={effort.id}
              disabled={disabled}
              onSelect={(event) => {
                keepMenuOpen(event);
                onEffortSelect(effort.id);
              }}
              className="min-h-11 items-start px-3 py-2 text-[15px]"
            >
              <span className="min-w-0 flex-1">
                <span className="block">
                  {EFFORT_NAMES[effort.id] ?? effort.id}
                </span>
                {effort.id === "ultra" ? (
                  <span className="text-muted-foreground mt-0.5 block text-xs leading-4">
                    {EFFORT_DESCRIPTIONS[effort.id]}
                  </span>
                ) : null}
              </span>
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      ) : (
        <p className="text-muted-foreground px-3 py-3 text-sm">
          Эта модель не поддерживает выбор усилия.
        </p>
      )}
    </>
  );
}

function SpeedItems({
  selectedModel,
  selectedServiceTier,
  disabled,
  onServiceTierSelect,
}: Pick<
  SelectorMenuProps,
  | "selectedModel"
  | "selectedServiceTier"
  | "disabled"
  | "onServiceTierSelect"
>) {
  const tiers = selectedModel?.serviceTiers ?? [];
  const value = selectedServiceTier ?? "standard";
  return (
    <>
      <DropdownMenuLabel className="text-muted-foreground px-3 pt-2 pb-1 text-sm font-normal">
        Скорость
      </DropdownMenuLabel>
      <DropdownMenuRadioGroup value={value}>
        <DropdownMenuRadioItem
          value="standard"
          disabled={disabled}
          onSelect={(event) => {
            keepMenuOpen(event);
            onServiceTierSelect(null);
          }}
          className="min-h-14 items-start px-3 py-2 text-[15px]"
        >
          <span className="min-w-0 flex-1">
            <span className="block">Стандартный</span>
            <span className="text-muted-foreground mt-0.5 block text-xs">
              Стандартная скорость
            </span>
          </span>
        </DropdownMenuRadioItem>
        {tiers.map((tier) => (
          <DropdownMenuRadioItem
            key={tier.id}
            value={tier.id}
            disabled={disabled}
            onSelect={(event) => {
              keepMenuOpen(event);
              onServiceTierSelect(tier.id);
            }}
            className="min-h-14 items-start px-3 py-2 text-[15px]"
          >
            <span className="min-w-0 flex-1">
              <span className="block">{serviceTierName(tier)}</span>
              <span className="text-muted-foreground mt-0.5 block text-xs leading-4">
                {tier.id === "priority"
                  ? "Скорость 1,5×, больше использования"
                  : tier.description}
              </span>
            </span>
          </DropdownMenuRadioItem>
        ))}
      </DropdownMenuRadioGroup>
    </>
  );
}

function DesktopSelectorMenu(props: SelectorMenuProps) {
  const effortName = props.selectedEffort
    ? EFFORT_NAMES[props.selectedEffort] ?? props.selectedEffort
    : "—";
  const selectedTier = props.selectedModel?.serviceTiers.find(
    (tier) => tier.id === props.selectedServiceTier,
  );

  return (
    <>
      <DropdownMenuSub>
        <DropdownMenuSubTrigger className="min-h-11 px-3 text-[15px]">
          <span>Модель</span>
          <span className="text-muted-foreground ml-auto max-w-32 truncate">
            {props.selectedModel
              ? compactModelName(props.selectedModel.displayName)
              : "—"}
          </span>
        </DropdownMenuSubTrigger>
        <DropdownMenuSubContent
          sideOffset={8}
          className="z-[90] w-72 rounded-2xl p-1.5"
        >
          <ModelItems
            models={props.models}
            selectedModelId={props.selectedModelId}
            disabled={props.disabled}
            onModelSelect={props.onModelSelect}
          />
        </DropdownMenuSubContent>
      </DropdownMenuSub>
      <DropdownMenuSub>
        <DropdownMenuSubTrigger
          disabled={
            !props.selectedModel ||
            props.selectedModel.supportedReasoningEfforts.length === 0
          }
          className="min-h-11 px-3 text-[15px]"
        >
          <span>Усилие</span>
          <span className="text-muted-foreground ml-auto max-w-36 truncate">
            {effortName}
          </span>
        </DropdownMenuSubTrigger>
        <DropdownMenuSubContent
          sideOffset={8}
          className="z-[90] w-80 rounded-2xl p-1.5"
        >
          <EffortItems
            selectedModel={props.selectedModel}
            selectedEffort={props.selectedEffort}
            disabled={props.disabled}
            onEffortSelect={props.onEffortSelect}
          />
        </DropdownMenuSubContent>
      </DropdownMenuSub>
      <DropdownMenuSub>
        <DropdownMenuSubTrigger
          disabled={props.selectedModel?.profile !== "codex-cli"}
          className="min-h-11 px-3 text-[15px]"
        >
          <span>Скорость</span>
          <span className="text-muted-foreground ml-auto max-w-28 truncate">
            {serviceTierName(selectedTier)}
          </span>
        </DropdownMenuSubTrigger>
        <DropdownMenuSubContent
          sideOffset={8}
          className="z-[90] w-80 rounded-2xl p-1.5"
        >
          <SpeedItems
            selectedModel={props.selectedModel}
            selectedServiceTier={props.selectedServiceTier}
            disabled={props.disabled}
            onServiceTierSelect={props.onServiceTierSelect}
          />
        </DropdownMenuSubContent>
      </DropdownMenuSub>
      <DropdownMenuSeparator />
      <DropdownMenuItem
        onSelect={() => openModelSettings()}
        className="text-muted-foreground min-h-10 px-3 text-[15px]"
      >
        <Settings2Icon className="size-4" aria-hidden="true" />
        Модели и подключения
      </DropdownMenuItem>
    </>
  );
}

function MobileSelectorMenu({
  page,
  onPageChange,
  ...props
}: SelectorMenuProps & {
  page: MobilePage;
  onPageChange: (page: MobilePage) => void;
}) {
  const backRef = useRef<HTMLButtonElement>(null);
  const modelRowRef = useRef<HTMLDivElement>(null);
  const effortRowRef = useRef<HTMLDivElement>(null);
  const speedRowRef = useRef<HTMLDivElement>(null);
  const selectedTier = props.selectedModel?.serviceTiers.find(
    (tier) => tier.id === props.selectedServiceTier,
  );
  const goTo = (next: Exclude<MobilePage, "root">) => {
    onPageChange(next);
    window.requestAnimationFrame(() => backRef.current?.focus());
  };
  const goBack = () => {
    const previous = page;
    onPageChange("root");
    window.setTimeout(() => {
      if (previous === "model") modelRowRef.current?.focus();
      if (previous === "effort") effortRowRef.current?.focus();
      if (previous === "speed") speedRowRef.current?.focus();
    }, 0);
  };

  if (page !== "root") {
    return (
      <>
        <div className="flex min-h-12 items-center border-b px-1">
          <Button
            ref={backRef}
            type="button"
            variant="ghost"
            size="sm"
            onPointerDown={(event) => event.stopPropagation()}
            onClick={(event) => {
              event.preventDefault();
              event.stopPropagation();
              goBack();
            }}
            className="min-h-11 rounded-xl px-2"
          >
            <ChevronLeftIcon className="size-4" aria-hidden="true" />
            Назад
          </Button>
          <span className="pr-3 text-sm font-medium">
            {page === "model"
              ? "Модель"
              : page === "effort"
                ? "Усилие"
                : "Скорость"}
          </span>
        </div>
        {page === "model" ? (
          <ModelItems
            models={props.models}
            selectedModelId={props.selectedModelId}
            disabled={props.disabled}
            onModelSelect={props.onModelSelect}
          />
        ) : null}
        {page === "effort" ? (
          <EffortItems
            selectedModel={props.selectedModel}
            selectedEffort={props.selectedEffort}
            disabled={props.disabled}
            onEffortSelect={props.onEffortSelect}
          />
        ) : null}
        {page === "speed" ? (
          <SpeedItems
            selectedModel={props.selectedModel}
            selectedServiceTier={props.selectedServiceTier}
            disabled={props.disabled}
            onServiceTierSelect={props.onServiceTierSelect}
          />
        ) : null}
      </>
    );
  }

  return (
    <>
      <DropdownMenuItem
        ref={modelRowRef}
        onSelect={(event) => {
          keepMenuOpen(event);
          goTo("model");
        }}
        className="min-h-14 rounded-2xl px-4 text-[18px]"
      >
        <span className="min-w-0 flex-1 truncate font-medium">
          {props.selectedModel?.displayName ?? "Выбрать модель"}
        </span>
        <ChevronRightIcon className="size-4" aria-hidden="true" />
      </DropdownMenuItem>
      <DropdownMenuSeparator />
      <DropdownMenuLabel className="text-muted-foreground px-4 pt-2 pb-1 text-[15px] font-semibold">
        Интеллект
      </DropdownMenuLabel>
      {props.selectedModel?.supportedReasoningEfforts.length ? (
        <DropdownMenuRadioGroup value={props.selectedEffort ?? ""}>
          {props.selectedModel.supportedReasoningEfforts.map((effort) => (
            <DropdownMenuRadioItem
              key={effort.id}
              ref={effort.id === props.selectedEffort ? effortRowRef : undefined}
              value={effort.id}
              disabled={props.disabled}
              onSelect={(event) => {
                keepMenuOpen(event);
                props.onEffortSelect(effort.id);
              }}
              className="min-h-12 rounded-xl px-4 text-[18px]"
            >
              {EFFORT_NAMES[effort.id] ?? effort.id}
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      ) : (
        <p className="text-muted-foreground px-4 py-3 text-sm">
          Для этой модели уровень интеллекта выбирается автоматически.
        </p>
      )}
      <DropdownMenuSeparator />
      <DropdownMenuItem
        ref={speedRowRef}
        disabled={props.selectedModel?.profile !== "codex-cli"}
        onSelect={(event) => {
          keepMenuOpen(event);
          goTo("speed");
        }}
        className="min-h-11 rounded-xl px-4 text-[15px]"
      >
        <span>Скорость</span>
        <span className="text-muted-foreground ml-auto max-w-28 truncate">
          {serviceTierName(selectedTier)}
        </span>
        <ChevronRightIcon className="size-4" aria-hidden="true" />
      </DropdownMenuItem>
    </>
  );
}

const ModelProfileSelectorControl: FC<{
  surface?: "composer" | "settings" | "mobile-header";
}> = ({ surface = "composer" }) => {
  const identity = useIdentity();
  const modelCatalog = useModelCatalog();
  const isRunning = useAuiState((state) => state.thread.isRunning);
  const [open, setOpen] = useState(false);
  const [mobilePage, setMobilePage] = useState<MobilePage>("root");
  const mobilePageRef = useRef<MobilePage>("root");
  const [error, setError] = useState<string | null>(null);
  const retryRef = useRef<(() => Promise<void>) | null>(null);
  const selectionInFlightRef = useRef(false);
  const isMobileSelector = useSyncExternalStore(
    subscribeMobileSelector,
    mobileSelectorSnapshot,
    serverMobileSelectorSnapshot,
  );

  const catalogModels = useMemo(() => {
    const models = modelCatalog.catalog?.models ?? FALLBACK_MODELS;
    const preferred = identity.user?.preferredModel;
    if (preferred && !models.some((model) => model.id === preferred)) {
      return [
        ...models,
        {
          id: preferred,
          profile: "codex-cli" as const,
          displayName: preferred,
          description: "Сохранённая модель временно недоступна.",
          available: false,
          supportedReasoningEfforts: [],
          serviceTiers: [],
          defaultReasoningEffort: null,
          isDefault: false,
          upgrade: null,
        },
      ];
    }
    return models;
  }, [identity.user?.preferredModel, modelCatalog.catalog?.models]);
  const modelOptions = useMemo(
    () => catalogModels.map(toModelOption),
    [catalogModels],
  );

  if (identity.status !== "authenticated" || !identity.user) return null;

  const selectedModelId = effectiveModelId(
    catalogModels,
    identity.user,
    modelCatalog.catalog?.configuredCodexModel ?? null,
  );
  const selectedModel = catalogModels.find(
    (model) => model.id === selectedModelId,
  );
  const selectedEffort =
    (selectedModel?.profile === "codex-cli"
      ? identity.user.preferredReasoningEffort ??
        selectedModel.defaultReasoningEffort ??
        modelCatalog.catalog?.configuredCodexEffort ??
        undefined
      : undefined);
  const selectedServiceTier = identity.user.preferredServiceTier;
  const selectedTier = selectedModel?.serviceTiers.find(
    (tier) => tier.id === selectedServiceTier,
  );
  const saving =
    identity.modelSettingsSaving || identity.agentProfileSaving;
  const disabled = saving || isRunning;
  const modelName = selectedModel
    ? compactModelName(selectedModel.displayName)
    : "Модель";
  const effortName = selectedEffort
    ? EFFORT_NAMES[selectedEffort] ?? selectedEffort
    : null;
  const speedName = serviceTierName(selectedTier);
  const triggerAccessibleLabel = [
    `Модель: ${modelName}`,
    effortName ? `Усилие: ${effortName}` : null,
    selectedModel?.profile === "codex-cli"
      ? `Скорость: ${speedName}`
      : null,
    "Открыть выбор",
  ]
    .filter(Boolean)
    .join(". ");

  const runSelection = async (
    action: () => Promise<void>,
    fallbackMessage: string,
  ) => {
    if (selectionInFlightRef.current) return;
    selectionInFlightRef.current = true;
    setError(null);
    try {
      await action();
      retryRef.current = null;
    } catch (requestError) {
      setError(
        requestError instanceof Error && requestError.message.trim()
          ? requestError.message
          : fallbackMessage,
      );
      retryRef.current = () => runSelection(action, fallbackMessage);
    } finally {
      selectionInFlightRef.current = false;
    }
  };

  const selectModel = async (value: string) => {
    if (
      isMobileSelector &&
      mobilePageRef.current !== "model"
    ) {
      return;
    }
    const model = catalogModels.find(
      (candidate) => candidate.id === value,
    );
    if (!model?.available || disabled) return;
    const currentEffort = identity.user?.preferredReasoningEffort;
    const nextEffort =
      model.profile === "codex-cli"
        ? model.supportedReasoningEfforts.some(
            (candidate) => candidate.id === currentEffort,
          )
          ? currentEffort ?? model.defaultReasoningEffort
          : model.defaultReasoningEffort
        : null;
    const currentTier = identity.user?.preferredServiceTier;
    const nextServiceTier =
      model.profile === "codex-cli" &&
      currentTier &&
      model.serviceTiers.some((tier) => tier.id === currentTier)
        ? currentTier
        : null;
    if (
      model.profile === identity.user?.preferredAgentProfile &&
      (model.profile !== "codex-cli" ||
        (model.id === identity.user.preferredModel &&
          nextEffort === identity.user?.preferredReasoningEffort &&
          nextServiceTier === identity.user?.preferredServiceTier))
    ) {
      return;
    }
    await runSelection(
      () =>
        identity.setModelSettings({
          profile: model.profile,
          model: model.profile === "auto" ? null : model.id,
          reasoningEffort: nextEffort,
          serviceTier: nextServiceTier,
        }),
      "Не удалось сменить модель.",
    );
  };

  const selectEffort = async (effort: string) => {
    if (
      disabled ||
      (isMobileSelector && mobilePageRef.current !== "effort") ||
      !selectedModel ||
      selectedModel.profile !== "codex-cli" ||
      !selectedModel.supportedReasoningEfforts.some(
        (candidate) => candidate.id === effort,
      ) ||
      effort === identity.user?.preferredReasoningEffort
    ) {
      return;
    }
    await runSelection(
      () =>
        identity.setModelSettings({
          profile: "codex-cli",
          model: selectedModel.id,
          reasoningEffort: effort,
          serviceTier: selectedServiceTier,
        }),
      "Не удалось изменить усилие.",
    );
  };

  const selectServiceTier = async (serviceTier: string | null) => {
    if (
      disabled ||
      (isMobileSelector && mobilePageRef.current !== "speed") ||
      !selectedModel ||
      selectedModel.profile !== "codex-cli" ||
      (serviceTier !== null &&
        !selectedModel.serviceTiers.some(
          (candidate) => candidate.id === serviceTier,
        )) ||
      serviceTier === identity.user?.preferredServiceTier
    ) {
      return;
    }
    await runSelection(
      () =>
        identity.setModelSettings({
          profile: "codex-cli",
          model: selectedModel.id,
          reasoningEffort: selectedEffort ?? null,
          serviceTier,
        }),
      "Не удалось изменить скорость.",
    );
  };

  const menuProps: SelectorMenuProps = {
    models: catalogModels,
    selectedModelId,
    selectedModel,
    selectedEffort,
    selectedServiceTier,
    disabled,
    saving,
    onModelSelect: (id) => void selectModel(id),
    onEffortSelect: (id) => void selectEffort(id),
    onServiceTierSelect: (id) => void selectServiceTier(id),
  };

  return (
    <div
      className={
        surface === "settings"
          ? "relative w-full"
          : surface === "mobile-header"
            ? "relative"
            : "relative min-w-0"
      }
    >
      <ModelSelector.Root
        models={modelOptions}
        value={selectedModelId}
        effort={selectedEffort}
      >
        <DropdownMenu
          open={open}
          onOpenChange={(nextOpen) => {
            setOpen(nextOpen);
            if (nextOpen) {
              mobilePageRef.current = "root";
              setMobilePage("root");
            }
          }}
        >
          <DropdownMenuTrigger asChild>
            <Button
              type="button"
              variant={surface === "settings" ? "outline" : "ghost"}
              disabled={isRunning}
              aria-busy={saving}
              aria-label={triggerAccessibleLabel}
              aria-describedby={error ? "model-selector-error" : undefined}
              className={
                surface === "settings"
                  ? "h-11 w-full justify-between rounded-xl px-3"
                  : surface === "mobile-header"
                    ? "h-11 gap-1 rounded-xl px-3 text-[21px] leading-none font-semibold tracking-[-0.035em] underline decoration-[1.5px] underline-offset-4"
                  : "h-11 max-w-[9rem] min-w-0 gap-1.5 rounded-full px-2 text-xs min-[960px]:h-9 min-[960px]:max-w-56 min-[960px]:px-3 min-[960px]:text-sm"
              }
            >
              {surface === "mobile-header" ? (
                <>
                  <span>Chat</span>
                  <ChevronDownIcon
                    className="text-muted-foreground size-5 shrink-0"
                    aria-hidden="true"
                  />
                </>
              ) : (
                <>
                  {saving ? (
                    <LoaderCircleIcon
                      className="size-3.5 shrink-0 animate-spin"
                      aria-hidden="true"
                    />
                  ) : (
                    <ZapIcon
                      className="size-3.5 shrink-0 fill-current"
                      aria-hidden="true"
                    />
                  )}
                  <span className="min-w-0 truncate">{modelName}</span>
                  {effortName ? (
                    <span className="text-muted-foreground hidden min-w-0 truncate min-[960px]:inline">
                      {effortName}
                    </span>
                  ) : null}
                  <ChevronDownIcon
                    className="text-muted-foreground size-3.5 shrink-0"
                    aria-hidden="true"
                  />
                </>
              )}
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent
            align={
              surface === "settings"
                ? "start"
                : surface === "mobile-header"
                  ? "center"
                  : isMobileSelector
                    ? "start"
                    : "end"
            }
            alignOffset={
              isMobileSelector && surface === "composer" ? 56 : 0
            }
            sideOffset={8}
            onEscapeKeyDown={(event) => {
              if (isMobileSelector && mobilePage !== "root") {
                event.preventDefault();
                setMobilePage("root");
              }
            }}
            onKeyDown={(event) => {
              if (
                isMobileSelector &&
                mobilePage !== "root" &&
                event.key === "ArrowLeft"
              ) {
                event.preventDefault();
                setMobilePage("root");
              }
            }}
            className={
              surface === "mobile-header"
                ? "z-[80] w-[min(24rem,calc(100vw-1.5rem))] rounded-[2rem] border-foreground/45 p-3 shadow-xl"
                : isMobileSelector
                  ? "z-[80] w-[min(15.5rem,calc(100vw-1.5rem))] rounded-[1.75rem] border-foreground/35 p-2 shadow-xl"
                  : "z-[80] w-[min(20rem,calc(100vw-1rem))] rounded-2xl p-1.5 shadow-xl"
            }
          >
            {isMobileSelector ? (
              <MobileSelectorMenu
                {...menuProps}
                page={mobilePage}
                onPageChange={(page) => {
                  mobilePageRef.current = page;
                  setMobilePage(page);
                }}
              />
            ) : (
              <DesktopSelectorMenu {...menuProps} />
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      </ModelSelector.Root>

      {error ? (
        <div
          id="model-selector-error"
          role="alert"
          className="border-destructive/25 bg-popover text-destructive absolute right-0 bottom-full z-[100] mb-2 flex w-72 items-center gap-2 rounded-xl border px-3 py-2 text-xs leading-relaxed shadow-lg"
        >
          <span className="min-w-0 flex-1">{error}</span>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-7 shrink-0 px-2 text-xs"
            onClick={() => void retryRef.current?.()}
          >
            Повторить
          </Button>
        </div>
      ) : null}
    </div>
  );
};

const ACCESS_OPTIONS: readonly {
  mode: DeveloperAccessMode;
  title: string;
  shortTitle: string;
  description: string;
}[] = [
  {
    mode: "standard",
    title: "Dev-режим выключен",
    shortTitle: "Dev-режим",
    description: "Обычные ответы без доступа к изменению кода",
  },
  {
    mode: "auto",
    title: "Dev-режим: с подтверждением",
    shortTitle: "Dev · С подтверждением",
    description: "Агент работает с кодом, опасные действия подтверждаются",
  },
  {
    mode: "full",
    title: "Dev-режим: полный доступ",
    shortTitle: "Dev · Полный доступ",
    description: "Полный доступ к рабочей среде без подтверждений",
  },
];

const DeveloperModeControl: FC<{
  surface?: "composer" | "settings" | "mobile-header";
}> = ({ surface = "composer" }) => {
  const developerMode = useDeveloperAgentMode();
  const isRunning = useAuiState((state) => state.thread.isRunning);
  const [open, setOpen] = useState(false);

  if (!developerMode.available) return null;

  const selected =
    ACCESS_OPTIONS.find((option) => option.mode === developerMode.mode) ??
    ACCESS_OPTIONS[0];
  const selectMode = (mode: DeveloperAccessMode) => {
    developerMode.setMode(mode);
    setOpen(false);
  };

  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <DropdownMenuTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          disabled={isRunning}
          aria-label={`${selected.title}. Открыть выбор Dev-режима`}
          className={
            surface === "settings"
              ? developerMode.mode === "full"
                ? "h-11 w-full justify-between rounded-xl px-3 text-orange-600"
                : "text-muted-foreground h-11 w-full justify-between rounded-xl px-3"
              : developerMode.mode === "full"
                ? "h-11 max-w-[10.5rem] min-w-0 gap-1.5 rounded-full px-2 text-orange-600 sm:h-9 sm:max-w-56 sm:px-3"
                : "text-muted-foreground h-11 max-w-[10.5rem] min-w-0 gap-1.5 rounded-full px-2 sm:h-9 sm:max-w-56 sm:px-3"
          }
        >
          {developerMode.mode === "full" ? (
            <ShieldAlertIcon className="size-4 shrink-0" aria-hidden="true" />
          ) : (
            <ShieldCheckIcon className="size-4 shrink-0" aria-hidden="true" />
          )}
          <span className="min-w-0 truncate text-xs sm:text-sm">
            {selected.shortTitle}
          </span>
          <ChevronDownIcon
            className="size-3.5 shrink-0 opacity-60"
            aria-hidden="true"
          />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align={surface === "settings" ? "start" : "start"}
        sideOffset={8}
        className="z-[90] w-[min(34rem,calc(100vw-1rem))] rounded-2xl p-2 shadow-xl"
      >
        <DropdownMenuLabel className="text-muted-foreground px-3 py-1 text-sm font-normal">
          Dev-режим
        </DropdownMenuLabel>
        <DropdownMenuRadioGroup value={developerMode.mode}>
          {ACCESS_OPTIONS.map((option) => (
            <DropdownMenuRadioItem
              key={option.mode}
              value={option.mode}
              onSelect={() => selectMode(option.mode)}
              className={
                option.mode === "full"
                  ? "min-h-14 items-start px-3 py-2 text-orange-600"
                  : "min-h-14 items-start px-3 py-2"
              }
            >
              <span className="min-w-0 flex-1">
                <span className="block text-sm font-medium">
                  {option.title}
                </span>
                <span className="text-muted-foreground mt-0.5 block text-xs leading-4">
                  {option.description}
                </span>
              </span>
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
};

export const AgentProfileSelector: FC<{
  surface?: "composer" | "settings" | "mobile-header";
  control?: "model" | "developer";
}> = ({ surface = "composer", control = "model" }) =>
  control === "developer" ? (
    <DeveloperModeControl surface={surface} />
  ) : (
    <ModelProfileSelectorControl surface={surface} />
  );
