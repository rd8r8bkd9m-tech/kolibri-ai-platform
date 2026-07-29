"use client";

import {
  type ComponentType,
  type KeyboardEvent,
  useEffect,
  useId,
  useRef,
  useState,
} from "react";
import {
  AlertTriangle,
  ArrowLeft,
  Bot,
  Calculator,
  CheckCircle2,
  CircleDot,
  Clock3,
  Database,
  FileSearch,
  Files as FilesIcon,
  FolderOpen,
  Globe2,
  Info,
  LockKeyhole,
  MessageCirclePlus,
  Paperclip,
  ShieldCheck,
  X,
  type LucideIcon,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

export const CONTEXT_PANEL_TABS = [
  { id: "review", label: "Проверка", icon: ShieldCheck },
  { id: "calculations", label: "Расчёты", icon: Calculator },
  { id: "browser", label: "Браузер", icon: Globe2 },
  { id: "files", label: "Файлы", icon: FilesIcon },
  {
    id: "subtask",
    label: "Дополнительная задача",
    icon: MessageCirclePlus,
  },
] as const satisfies ReadonlyArray<{
  id: string;
  label: string;
  icon: LucideIcon;
}>;

export type ContextPanelMode = (typeof CONTEXT_PANEL_TABS)[number]["id"];

export interface ContextPanelProps {
  projectName?: string;
  mode?: ContextPanelMode;
  onClose?: () => void;
  onOpenSettings?: () => void;
}

type EmptyStateProps = {
  action?: {
    label: string;
    onClick: () => void;
  };
  icon: LucideIcon;
  title: string;
  description: string;
  detail?: string;
};

function isContextPanelMode(value: unknown): value is ContextPanelMode {
  return CONTEXT_PANEL_TABS.some((tab) => tab.id === value);
}

function CloseButton({ onClose }: { onClose: () => void }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          onClick={onClose}
          className="text-muted-foreground hover:text-foreground"
        >
          <X aria-hidden="true" />
          <span className="sr-only">Закрыть панель инструментов</span>
        </Button>
      </TooltipTrigger>
      <TooltipContent side="bottom" sideOffset={6}>
        Закрыть панель
      </TooltipContent>
    </Tooltip>
  );
}

function EmptyState({
  action,
  icon: Icon,
  title,
  description,
  detail,
}: EmptyStateProps) {
  return (
    <div className="flex min-h-72 flex-col items-center justify-center px-5 py-10 text-center">
      <span className="border-border bg-muted/45 text-muted-foreground mb-4 grid size-11 place-items-center rounded-xl border">
        <Icon className="size-5" aria-hidden="true" />
      </span>
      <h3 className="text-sm font-semibold">{title}</h3>
      <p className="text-muted-foreground mt-1.5 max-w-xs text-xs leading-relaxed">
        {description}
      </p>
      {detail ? (
        <p className="border-border bg-muted/20 text-muted-foreground mt-4 max-w-xs rounded-lg border px-3 py-2.5 text-[11px] leading-relaxed">
          {detail}
        </p>
      ) : null}
      {action ? (
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="mt-4 rounded-lg shadow-none"
          onClick={action.onClick}
        >
          {action.label}
        </Button>
      ) : null}
    </div>
  );
}

type TruthKind = {
  id: "facts" | "assumptions" | "decisions";
  label: string;
  emptyLabel: string;
  description: string;
  icon: LucideIcon;
};

const TRUTH_KINDS: readonly TruthKind[] = [
  {
    id: "facts",
    label: "Факты",
    emptyLabel: "Подтверждённых фактов нет",
    description: "Появятся только данные с источником и временем проверки.",
    icon: Database,
  },
  {
    id: "assumptions",
    label: "Допущения",
    emptyLabel: "Допущения не зафиксированы",
    description: "Каждое допущение будет помечено с основанием и влиянием.",
    icon: CircleDot,
  },
  {
    id: "decisions",
    label: "Решения",
    emptyLabel: "Утверждённых решений нет",
    description: "Предложения не считаются решениями без явного утверждения.",
    icon: CheckCircle2,
  },
];

function ReviewPanel() {
  return (
    <div>
      <section
        className="border-border/80 border-b px-4 py-4"
        aria-labelledby="version-state-title"
      >
        <div className="flex items-start justify-between gap-3">
          <div>
            <p
              id="version-state-title"
              className="text-xs font-semibold"
            >
              Состояние версии
            </p>
            <p className="text-muted-foreground mt-0.5 text-[11px]">
              Данные проекта не подключены
            </p>
          </div>
          <span className="text-muted-foreground text-[10px] font-medium whitespace-nowrap">
            Нет версии
          </span>
        </div>
        <dl className="mt-4 grid grid-cols-[1fr_auto] gap-x-4 gap-y-2 text-xs">
          <dt className="text-muted-foreground">Входные данные</dt>
          <dd className="font-medium">—</dd>
          <dt className="text-muted-foreground">Последняя проверка</dt>
          <dd className="font-medium">—</dd>
          <dt className="text-muted-foreground">Доказательства</dt>
          <dd className="font-medium tabular-nums">0</dd>
          <dt className="text-muted-foreground">Выпуск</dt>
          <dd className="font-medium">Недоступен</dd>
        </dl>
      </section>

      <section
        className="border-border/80 border-b px-4 py-3.5"
        aria-labelledby="stale-policy-title"
      >
        <div className="flex items-start gap-2.5">
          <AlertTriangle
            className="text-muted-foreground mt-0.5 size-4 shrink-0"
            aria-hidden="true"
          />
          <div>
            <h3 id="stale-policy-title" className="text-xs font-semibold">
              Правило выпуска
            </h3>
            <p className="text-muted-foreground mt-1 text-[11px] leading-relaxed">
              Изменение входных данных требует повторной проверки зависимых
              результатов.
            </p>
          </div>
        </div>
      </section>

      <section aria-labelledby="truth-register-title">
        <div className="border-border/80 flex items-center justify-between gap-2 border-b px-4 py-3">
          <h3
            id="truth-register-title"
            className="text-xs font-semibold"
          >
            Реестр контекста
          </h3>
          <span className="text-muted-foreground text-[10px]">Пустой</span>
        </div>
        <div className="divide-border divide-y">
          {TRUTH_KINDS.map(
            ({
              id,
              label,
              emptyLabel,
              description,
              icon: Icon,
            }) => (
              <section
                key={id}
                data-truth-kind={id}
                className="flex items-start gap-2.5 px-4 py-3"
                aria-labelledby={`truth-kind-${id}`}
              >
                <span className="text-muted-foreground mt-0.5 grid size-6 shrink-0 place-items-center">
                  <Icon className="size-3.5" aria-hidden="true" />
                </span>
                <div className="min-w-0">
                  <h4
                    id={`truth-kind-${id}`}
                    className="text-xs font-semibold"
                  >
                    {label}
                  </h4>
                  <p className="mt-0.5 text-[11px] font-medium">{emptyLabel}</p>
                  <p className="text-muted-foreground mt-0.5 text-[10px] leading-relaxed">
                    {description}
                  </p>
                </div>
              </section>
            ),
          )}
        </div>
      </section>

      <section
        className="border-border/80 flex items-start gap-2.5 border-t px-4 py-4"
        aria-labelledby="evidence-empty-title"
      >
        <Paperclip
          className="text-muted-foreground mt-0.5 size-4 shrink-0"
          aria-hidden="true"
        />
        <div>
          <h3 id="evidence-empty-title" className="text-xs font-medium">
            Доказательства не приложены
          </h3>
          <p className="text-muted-foreground mt-1 text-[10px] leading-relaxed">
            Источники и результаты проверки появятся после загрузки данных.
          </p>
        </div>
      </section>
    </div>
  );
}

function CalculationsPanel() {
  return (
    <section
      className="flex h-full min-h-0 flex-col"
      aria-labelledby="calculations-title"
    >
      <div className="border-border/80 border-b px-4 py-3">
        <h3 id="calculations-title" className="text-xs font-semibold">
          Расчёты проекта
        </h3>
        <p className="text-muted-foreground mt-0.5 text-[10px]">
          Подтверждённых расчётных версий нет
        </p>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <EmptyState
          icon={Calculator}
          title="Расчёты пока не созданы"
          description="Позиции, объёмы и цены появятся после получения исходных данных и будут связаны с их источниками."
          detail="Пустая таблица не подменяется примерными значениями."
        />
      </div>

      <footer className="border-border/80 text-muted-foreground flex min-h-9 items-center border-t px-4 text-[10px]">
        Итог появится только для сохранённой расчётной версии
      </footer>
    </section>
  );
}

function BrowserPanel({ onOpenSettings }: { onOpenSettings?: () => void }) {
  return (
    <section
      className="flex h-full min-h-0 flex-col"
      aria-labelledby="browser-view-title"
    >
      <h2 id="browser-view-title" className="sr-only">
        Браузер маркетплейсов
      </h2>
      <header className="border-border/70 bg-muted/10 flex h-12 shrink-0 items-center gap-1 border-b px-2">
        <div className="border-border bg-background flex h-9 min-w-0 flex-1 items-center gap-2 rounded-xl border px-3">
          <LockKeyhole
            className="text-muted-foreground size-3 shrink-0"
            aria-hidden="true"
          />
          <span className="min-w-0 truncate text-xs">
            kolibri://marketplaces
          </span>
        </div>
      </header>

      <div
        className="flex min-h-0 flex-1 flex-col overflow-y-auto"
        role="status"
      >
        <div className="my-auto">
          <EmptyState
            icon={Globe2}
            title="Подключения маркетплейсов не настроены"
            description="После подключения в личном кабинете здесь появятся предложения только из разрешённых источников."
            detail="Kolibri не показывает примерные цены и не добавляет позиции в проект без полученных данных."
            action={
              onOpenSettings
                ? {
                    label: "Открыть личный кабинет",
                    onClick: onOpenSettings,
                  }
                : undefined
            }
          />
        </div>
        <footer className="border-border/70 text-muted-foreground flex min-h-9 shrink-0 items-center border-t px-4 text-[10px]">
          Нет активных подключений
        </footer>
      </div>
    </section>
  );
}

function FilesPanel() {
  return (
    <div className="p-3 sm:p-4">
      <section
        className="border-border bg-card overflow-hidden rounded-xl border"
        aria-labelledby="context-files-empty-title"
      >
        <header className="border-border/70 flex items-center justify-between border-b px-3.5 py-3">
          <div>
            <h3 className="text-xs font-semibold">Файлы контекста</h3>
            <p className="text-muted-foreground mt-0.5 text-[10px]">
              Вложения и версии
            </p>
          </div>
          <span className="bg-muted text-muted-foreground rounded-full px-2 py-1 text-[10px] tabular-nums">
            0
          </span>
        </header>
        <div className="border-border/70 text-muted-foreground grid grid-cols-[1fr_auto] border-b px-3.5 py-2 text-[10px] font-medium">
          <span>Имя</span>
          <span>Версия</span>
        </div>
        <EmptyState
          icon={FolderOpen}
          title="Файлы не прикреплены"
          description="Загруженные пользователем файлы и созданные артефакты появятся здесь с точной версией."
          detail="Пустое состояние не означает, что файлы проекта были удалены или обработаны."
        />
        <span id="context-files-empty-title" className="sr-only">
          Пустое состояние файлов
        </span>
      </section>
    </div>
  );
}

function SubtaskPanel() {
  return (
    <div className="space-y-3 p-3 sm:p-4">
      <section
        className="border-border bg-card rounded-xl border p-3.5"
        aria-labelledby="subtask-empty-title"
      >
        <div className="flex items-start gap-3">
          <span className="bg-muted text-muted-foreground grid size-9 shrink-0 place-items-center rounded-lg">
            <MessageCirclePlus className="size-4" aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <h3 id="subtask-empty-title" className="text-xs font-semibold">
              Дополнительная задача не выбрана
            </h3>
            <p className="text-muted-foreground mt-1 text-[11px] leading-relaxed">
              Назначение, исполнитель и состояние появятся из логического
              контура управления. Эта панель не создаёт задачи самостоятельно.
            </p>
          </div>
        </div>
      </section>

      <dl className="border-border bg-card divide-border overflow-hidden rounded-xl border text-xs">
        <div className="flex items-center justify-between gap-3 px-3.5 py-3">
          <dt className="text-muted-foreground flex items-center gap-2">
            <Bot className="size-3.5" aria-hidden="true" />
            Исполнитель
          </dt>
          <dd className="font-medium">—</dd>
        </div>
        <div className="flex items-center justify-between gap-3 border-t px-3.5 py-3">
          <dt className="text-muted-foreground flex items-center gap-2">
            <Clock3 className="size-3.5" aria-hidden="true" />
            Состояние
          </dt>
          <dd className="font-medium">Не выбрана</dd>
        </div>
        <div className="flex items-center justify-between gap-3 border-t px-3.5 py-3">
          <dt className="text-muted-foreground flex items-center gap-2">
            <FileSearch className="size-3.5" aria-hidden="true" />
            Результат
          </dt>
          <dd className="font-medium">—</dd>
        </div>
      </dl>

      <div className="border-border bg-muted/20 text-muted-foreground flex items-start gap-2 rounded-xl border px-3.5 py-3 text-[10px] leading-relaxed">
        <Info className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
        Служебная переписка агентов здесь не показывается. Пользователь видит
        проверяемое состояние и готовый результат.
      </div>
    </div>
  );
}

const PANEL_CONTENT: Record<ContextPanelMode, ComponentType> = {
  review: ReviewPanel,
  calculations: CalculationsPanel,
  browser: BrowserPanel,
  files: FilesPanel,
  subtask: SubtaskPanel,
};

export function ContextPanel({
  projectName,
  mode = "review",
  onClose,
  onOpenSettings,
}: ContextPanelProps) {
  const initialMode = isContextPanelMode(mode) ? mode : "review";
  const [activeTab, setActiveTab] = useState<ContextPanelMode>(initialMode);
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const generatedId = useId().replace(/:/g, "");
  const projectLabel = projectName?.trim() || "Проект не выбран";

  useEffect(() => {
    if (isContextPanelMode(mode)) {
      setActiveTab(mode);
    }
  }, [mode]);

  const activeDefinition =
    CONTEXT_PANEL_TABS.find((tab) => tab.id === activeTab) ??
    CONTEXT_PANEL_TABS[0];
  const browserOnly = activeTab === "browser";
  function focusTabAt(index: number) {
    const nextIndex =
      (index + CONTEXT_PANEL_TABS.length) % CONTEXT_PANEL_TABS.length;
    const nextTab = CONTEXT_PANEL_TABS[nextIndex];
    setActiveTab(nextTab.id);
    tabRefs.current[nextIndex]?.focus();
  }

  function handleTabKeyDown(
    event: KeyboardEvent<HTMLButtonElement>,
    index: number,
  ) {
    if (event.key === "ArrowRight") {
      event.preventDefault();
      focusTabAt(index + 1);
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      focusTabAt(index - 1);
    } else if (event.key === "Home") {
      event.preventDefault();
      focusTabAt(0);
    } else if (event.key === "End") {
      event.preventDefault();
      focusTabAt(CONTEXT_PANEL_TABS.length - 1);
    }
  }

  return (
    <TooltipProvider delayDuration={300}>
      <aside
        data-testid="context-panel"
        data-context-mode={activeTab}
        className="bg-background flex h-full min-h-0 min-w-0 flex-col overflow-hidden"
        aria-label="Панель инструментов проекта"
      >
        {!browserOnly ? (
          <header className="border-border/80 flex h-11 shrink-0 items-center justify-between gap-3 border-b px-3">
          <div className="min-w-0">
            <h2 className="truncate text-sm font-semibold">
              {activeDefinition.label}
            </h2>
            <p className="text-muted-foreground truncate text-[11px]">
              {projectLabel}
            </p>
          </div>
          {onClose ? <CloseButton onClose={onClose} /> : null}
          </header>
        ) : null}

        {!browserOnly ? (
          <div
            role="tablist"
            aria-label="Инструменты рабочего пространства"
            aria-orientation="horizontal"
            className="border-border/80 grid grid-cols-5 border-b"
          >
          {CONTEXT_PANEL_TABS.map(({ id, label, icon: Icon }, index) => {
            const isActive = activeTab === id;
            const tabId = `${generatedId}-${id}-tab`;
            const panelId = `${generatedId}-${id}-panel`;

            return (
              <Tooltip key={id}>
                <TooltipTrigger asChild>
                  <button
                    ref={(node) => {
                      tabRefs.current[index] = node;
                    }}
                    id={tabId}
                    type="button"
                    role="tab"
                    aria-selected={isActive}
                    aria-controls={panelId}
                    tabIndex={isActive ? 0 : -1}
                    onClick={() => setActiveTab(id)}
                    onKeyDown={(event) => handleTabKeyDown(event, index)}
                    className={cn(
                      "relative flex h-9 min-w-0 items-center justify-center gap-1.5 px-1 text-[10px] transition-colors outline-none focus-visible:z-10 focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring",
                      isActive
                        ? "text-foreground bg-muted/30"
                        : "text-muted-foreground hover:bg-muted/25 hover:text-foreground",
                    )}
                  >
                    <Icon className="size-3.5" aria-hidden="true" />
                    <span className="w-full truncate">{label}</span>
                    <span
                      className={cn(
                        "bg-primary absolute inset-x-2 bottom-0 h-0.5 rounded-full transition-opacity",
                        isActive ? "opacity-100" : "opacity-0",
                      )}
                      aria-hidden="true"
                    />
                  </button>
                </TooltipTrigger>
                <TooltipContent side="bottom" sideOffset={8}>
                  {label}
                </TooltipContent>
              </Tooltip>
            );
          })}
          </div>
        ) : null}

        <div className="min-h-0 flex-1">
          {CONTEXT_PANEL_TABS.map(({ id }) => {
            const PanelContent = PANEL_CONTENT[id];
            const isActive = activeTab === id;

            return (
              <div
                key={id}
                id={`${generatedId}-${id}-panel`}
                role="tabpanel"
                aria-labelledby={`${generatedId}-${id}-tab`}
                tabIndex={isActive ? 0 : -1}
                hidden={!isActive}
                className="h-full min-h-0 overflow-y-auto outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
              >
                {isActive ? (
                  id === "browser" ? (
                    <BrowserPanel onOpenSettings={onOpenSettings} />
                  ) : (
                    <PanelContent />
                  )
                ) : null}
              </div>
            );
          })}
        </div>

      </aside>
    </TooltipProvider>
  );
}
