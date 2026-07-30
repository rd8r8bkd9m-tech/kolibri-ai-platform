"use client";

import {
  useEffect,
  useId,
  useState,
  type ComponentType,
  type ReactNode,
} from "react";
import {
  Braces,
  Calculator,
  CheckCircle2,
  ClipboardPlus,
  FilePenLine,
  Files,
  FileSpreadsheet,
  FileText,
  FolderOpen,
  Folders,
  Globe,
  LayoutList,
  LayoutDashboard,
  Maximize2,
  MessageCirclePlus,
  Minus,
  Minimize2,
  PanelBottom,
  PanelRight,
  ShieldCheck,
  Table2,
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
import {
  ContextPanel,
  type ContextPanelMode,
} from "@/components/kolibri-workspace/context-panel";
import { WorkspaceArtifactEditor } from "@/components/kolibri-workspace/workspace-artifact-editor";
import {
  WorkspaceFileManager,
  type WorkspaceFile,
  type WorkspaceFileCategory,
} from "@/components/kolibri-workspace/workspace-file-manager";
import type { WorkspaceCatalogLoadState } from "@/lib/workspace-documents";

export const CANVAS_VIEW_ALLOWLIST = [
  "estimate",
  "document",
  "editor",
  "files",
] as const;

export type CanvasMode = (typeof CANVAS_VIEW_ALLOWLIST)[number];
export type CanvasPlacement = "bottom" | "primary" | "right";

export type CanvasSessionTabPresentation = {
  id: string;
  title: string;
};

export interface CanvasWorkspaceProps {
  activeSessionTabId?: string;
  compactChrome?: boolean;
  fileCategory?: WorkspaceFileCategory;
  maximized?: boolean;
  projectName?: string;
  mode?: CanvasMode;
  onClose?: () => void;
  onFilesBack?: () => void;
  onMinimize?: () => void;
  onOpenDesktop?: () => void;
  onOpenSettings?: () => void;
  onRetryWorkspaceCatalog?: () => void;
  onSelectedFileChange?: (file: WorkspaceFile | null) => void;
  onPlacementChange?: (placement: CanvasPlacement) => void;
  onSessionTabSelect?: (tabId: string) => void;
  onToolModeChange?: (mode: ContextPanelMode | null) => void;
  onToggleMaximize?: () => void;
  placement?: CanvasPlacement;
  selectedFile?: WorkspaceFile | null;
  sessionTabs?: readonly CanvasSessionTabPresentation[];
  surfaceContent?: ReactNode;
  surfaceMode?: string;
  toolMode?: ContextPanelMode | null;
  workspaceFiles?: readonly WorkspaceFile[];
  workspaceCatalogState?: WorkspaceCatalogLoadState;
}

type CanvasViewProps = {
  projectLabel: string;
};

type CanvasViewDefinition = {
  label: string;
  description: string;
  icon: LucideIcon;
  component: ComponentType<CanvasViewProps>;
};

function isCanvasMode(value: unknown): value is CanvasMode {
  return CANVAS_VIEW_ALLOWLIST.includes(value as CanvasMode);
}

function IconAction({
  label,
  children,
  className,
  ...props
}: React.ComponentProps<typeof Button> & {
  label: string;
  children: ReactNode;
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="icon-xs"
          className={cn(
            "text-muted-foreground size-7 rounded-lg",
            className,
          )}
          {...props}
        >
          {children}
          <span className="sr-only">{label}</span>
        </Button>
      </TooltipTrigger>
      <TooltipContent side="bottom" sideOffset={6}>
        {label}
      </TooltipContent>
    </Tooltip>
  );
}

function EstimateView({ projectLabel }: CanvasViewProps) {
  return (
    <section
      className="bg-background flex min-h-0 flex-1 flex-col"
      aria-labelledby="estimate-preview-title"
    >
      <header className="border-border/80 flex min-h-12 items-center justify-between gap-3 border-b px-3 @min-[560px]:px-4">
        <div className="min-w-0">
          <h2 id="estimate-preview-title" className="truncate text-sm font-medium">
            Черновик сметы
          </h2>
          <p className="text-muted-foreground truncate text-[11px]">
            {projectLabel}
          </p>
        </div>
      </header>

      <div className="min-h-0 flex-1 overflow-auto">
        <table className="h-full w-full min-w-[680px] border-collapse text-left text-xs">
          <caption className="sr-only">Редактор сметы без позиций</caption>
          <thead>
            <tr className="border-border text-muted-foreground border-b">
              <th className="w-12 px-3 py-2.5 font-medium" scope="col">
                №
              </th>
              <th className="min-w-60 px-3 py-2.5 font-medium" scope="col">
                Наименование
              </th>
              <th className="w-24 px-3 py-2.5 font-medium" scope="col">
                Ед. изм.
              </th>
              <th className="w-28 px-3 py-2.5 text-right font-medium" scope="col">
                Количество
              </th>
              <th className="w-28 px-3 py-2.5 text-right font-medium" scope="col">
                Цена
              </th>
              <th className="w-32 px-3 py-2.5 text-right font-medium" scope="col">
                Стоимость
              </th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td colSpan={6} className="h-full px-6 py-16 text-center">
                <div className="text-muted-foreground mx-auto flex max-w-xs flex-col items-center">
                  <Table2 className="mb-3 size-5" aria-hidden="true" />
                  <p className="text-foreground text-sm font-medium">
                    Пока нет позиций
                  </p>
                  <p className="mt-1 text-xs">
                    Добавьте исходные данные в диалоге.
                  </p>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <footer className="border-border/80 text-muted-foreground flex min-h-9 items-center justify-between gap-3 border-t px-3 text-[11px] @min-[560px]:px-4">
        <span>Нет расчётной версии</span>
        <span className="text-foreground font-medium tabular-nums">Итого —</span>
      </footer>
    </section>
  );
}

function DocumentView({ projectLabel }: CanvasViewProps) {
  return (
    <div className="grid min-h-0 flex-1 grid-cols-1 @min-[760px]:grid-cols-[184px_minmax(0,1fr)]">
      <aside className="border-border/80 bg-muted/20 hidden border-r p-3 @min-[760px]:block">
        <div className="text-muted-foreground mb-3 flex items-center gap-2 px-2 text-[11px] font-semibold tracking-wide uppercase">
          <LayoutList className="size-3.5" aria-hidden="true" />
          Оглавление
        </div>
        <div className="border-border text-muted-foreground rounded-lg border border-dashed px-3 py-5 text-center text-[11px] leading-relaxed">
          Разделы документа ещё не созданы
        </div>
      </aside>

      <section
        className="min-h-0 overflow-auto bg-stone-100/70 p-3 dark:bg-black/15 @min-[540px]:p-5 @min-[820px]:p-8"
        aria-labelledby="document-preview-title"
      >
        <article className="border-border/80 bg-card mx-auto min-h-[680px] w-full max-w-[760px] rounded-sm border px-6 py-8 shadow-[0_18px_50px_-34px_rgba(15,23,42,0.55)] @min-[560px]:px-12 @min-[560px]:py-12">
          <div className="border-border/70 text-muted-foreground flex flex-wrap items-center justify-between gap-2 border-b pb-4 text-[10px] tracking-wide uppercase">
            <span>{projectLabel}</span>
            <span>Предпросмотр документа</span>
          </div>

          <div className="mx-auto flex min-h-[520px] max-w-xl flex-col items-center justify-center text-center">
            <span className="bg-muted text-muted-foreground mb-5 grid size-12 place-items-center rounded-xl">
              <FileText className="size-6" aria-hidden="true" />
            </span>
            <p className="text-muted-foreground mb-2 text-xs font-medium tracking-wide uppercase">
              Черновик без версии
            </p>
            <h2
              id="document-preview-title"
              className="text-2xl font-semibold tracking-tight @min-[560px]:text-3xl"
            >
              Документ ещё не сформирован
            </h2>
            <p className="text-muted-foreground mt-3 max-w-md text-sm leading-6">
              Заголовок, реквизиты и содержание появятся после выбора
              проверенного шаблона и подтверждения входных данных.
            </p>
            <div className="mt-8 w-full space-y-3" aria-hidden="true">
              <div className="bg-muted/70 mx-auto h-2 w-4/5 rounded-full" />
              <div className="bg-muted/70 mx-auto h-2 w-full rounded-full" />
              <div className="bg-muted/70 mx-auto h-2 w-11/12 rounded-full" />
              <div className="bg-muted/70 mx-auto h-2 w-3/5 rounded-full" />
            </div>
          </div>

          <div className="border-border/70 text-muted-foreground flex items-center justify-between border-t pt-4 text-[10px]">
            <span>Предпросмотр, не выпуск</span>
            <span>Версия —</span>
          </div>
        </article>
      </section>
    </div>
  );
}

const ALLOWED_BLOCKS = [
  { label: "Заголовок", icon: FilePenLine },
  { label: "Текст", icon: LayoutList },
  { label: "Таблица", icon: Table2 },
  { label: "Доказательство", icon: ShieldCheck },
  { label: "Ссылка на файл", icon: FolderOpen },
] as const;

function EditorView({ projectLabel }: CanvasViewProps) {
  return (
    <div className="grid min-h-0 flex-1 grid-cols-1 @min-[960px]:grid-cols-[192px_minmax(0,1fr)_204px]">
      <aside className="border-border/80 bg-muted/20 hidden min-h-0 border-r p-3 @min-[960px]:block">
        <div className="text-muted-foreground mb-3 flex items-center gap-2 px-2 text-[11px] font-semibold tracking-wide uppercase">
          <Braces className="size-3.5" aria-hidden="true" />
          Разрешённые блоки
        </div>
        <ul className="space-y-1" aria-label="Разрешённые компоненты редактора">
          {ALLOWED_BLOCKS.map(({ label, icon: Icon }) => (
            <li
              key={label}
              className="border-border/70 bg-background text-muted-foreground flex items-center gap-2 rounded-md border px-2.5 py-2 text-xs"
            >
              <Icon className="size-3.5" aria-hidden="true" />
              {label}
            </li>
          ))}
        </ul>
      </aside>

      <section
        className="min-h-0 overflow-auto bg-[linear-gradient(to_right,rgba(120,120,120,0.055)_1px,transparent_1px),linear-gradient(to_bottom,rgba(120,120,120,0.055)_1px,transparent_1px)] bg-[size:24px_24px] p-3 @min-[560px]:p-5"
        aria-labelledby="editor-preview-title"
      >
        <div className="border-border/80 bg-card mx-auto flex min-h-[520px] w-full max-w-3xl flex-col rounded-xl border shadow-[0_18px_50px_-36px_rgba(15,23,42,0.55)]">
          <header className="border-border/70 border-b px-4 py-3">
            <p className="text-muted-foreground text-[11px]">{projectLabel}</p>
            <h2
              id="editor-preview-title"
              className="mt-0.5 text-sm font-semibold"
            >
              Декларативный редактор
            </h2>
          </header>
          <div className="flex flex-1 items-center justify-center p-5">
            <div className="border-border text-muted-foreground flex w-full max-w-md flex-col items-center rounded-xl border border-dashed px-6 py-12 text-center">
              <FilePenLine className="mb-3 size-7" aria-hidden="true" />
              <p className="text-foreground text-sm font-medium">
                Полотно пусто
              </p>
              <p className="mt-1.5 text-xs leading-relaxed">
                Компоненты появятся после получения типизированного дерева.
                Произвольные разметка и сценарии не принимаются.
              </p>
            </div>
          </div>
          <footer className="border-border/70 text-muted-foreground flex flex-wrap items-center gap-x-4 gap-y-2 border-t px-4 py-2.5 text-[10px]">
            <span className="flex items-center gap-1.5">
              <CheckCircle2 className="size-3 text-teal-600" aria-hidden="true" />
              Только компоненты из разрешённого набора
            </span>
            <span>Схема не загружена</span>
          </footer>
        </div>
      </section>

      <aside className="border-border/80 bg-muted/20 hidden min-h-0 border-l p-3 @min-[960px]:block">
        <div className="text-muted-foreground mb-3 text-[11px] font-semibold tracking-wide uppercase">
          Свойства
        </div>
        <div className="border-border text-muted-foreground rounded-lg border border-dashed px-3 py-5 text-center text-[11px] leading-relaxed">
          Выберите разрешённый блок, чтобы увидеть его типизированные свойства
        </div>
      </aside>
    </div>
  );
}

function FilesView({ projectLabel }: CanvasViewProps) {
  return (
    <section
      className="flex min-h-0 flex-1 flex-col"
      aria-labelledby="files-preview-title"
    >
      <header className="border-border/70 bg-muted/15 flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3">
        <div className="min-w-0">
          <p className="text-muted-foreground truncate text-[11px]">
            {projectLabel} / Файлы проекта
          </p>
          <h2 id="files-preview-title" className="mt-0.5 text-sm font-semibold">
            Файловый менеджер
          </h2>
        </div>
      </header>

      <div className="border-border/70 text-muted-foreground hidden grid-cols-[minmax(0,1fr)_120px_120px] border-b px-4 py-2 text-[11px] font-medium @min-[560px]:grid">
        <span>Имя</span>
        <span>Версия</span>
        <span>Статус</span>
      </div>

      <div className="flex flex-1 items-center justify-center p-6">
        <div className="max-w-sm text-center">
          <span className="bg-muted text-muted-foreground mx-auto mb-4 grid size-12 place-items-center rounded-xl">
            <FolderOpen className="size-6" aria-hidden="true" />
          </span>
          <p className="text-sm font-medium">Файлы не загружены</p>
          <p className="text-muted-foreground mt-1.5 text-xs leading-relaxed">
            Проверенные вложения, документы и их версии появятся здесь после
            получения данных проекта.
          </p>
          <div className="border-border bg-muted/20 text-muted-foreground mt-4 rounded-lg border px-3 py-2.5 text-[11px]">
            Пустое состояние — это не утверждение об артефактах проекта
          </div>
        </div>
      </div>
    </section>
  );
}

const CANVAS_VIEW_DEFINITIONS: Record<CanvasMode, CanvasViewDefinition> = {
  estimate: {
    label: "Смета",
    description: "Табличный расчёт",
    icon: FileSpreadsheet,
    component: EstimateView,
  },
  document: {
    label: "Документ",
    description: "Лист предпросмотра",
    icon: FileText,
    component: DocumentView,
  },
  editor: {
    label: "Редактор",
    description: "Типизированные блоки",
    icon: FilePenLine,
    component: EditorView,
  },
  files: {
    label: "Файлы",
    description: "Версии и вложения",
    icon: Files,
    component: FilesView,
  },
};

const WORKSPACE_TOOLS = [
  {
    id: "review",
    label: "Проверка",
    shortcut: "⌃⇧G",
    icon: ClipboardPlus,
  },
  {
    id: "calculations",
    label: "Расчёты",
    shortcut: null,
    icon: Calculator,
  },
  {
    id: "browser",
    label: "Браузер",
    shortcut: "⌘T",
    icon: Globe,
  },
  {
    id: "files",
    label: "Файлы",
    shortcut: "⌘P",
    icon: Folders,
  },
  {
    id: "subtask",
    label: "Дополнительная задача",
    shortcut: "⌥⌘S",
    icon: MessageCirclePlus,
  },
] as const satisfies ReadonlyArray<{
  id: ContextPanelMode;
  label: string;
  shortcut: string | null;
  icon: LucideIcon;
}>;

function WorkspaceLauncher({
  onSelect,
}: {
  onSelect: (mode: ContextPanelMode) => void;
}) {
  return (
    <nav
      aria-label="Инструменты рабочей области"
      className="flex min-h-0 flex-1 items-center justify-center px-5 py-10 @min-[640px]:px-10"
    >
      <ul className="w-full max-w-[22rem]">
        {WORKSPACE_TOOLS.map(({ id, icon: Icon, label, shortcut }) => (
          <li key={id}>
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  onClick={() => onSelect(id)}
                  className="hover:bg-muted/55 focus-visible:ring-ring flex h-11 w-full items-center gap-3 rounded-lg px-3 text-left text-[13px] font-medium transition-colors outline-none focus-visible:ring-2"
                >
                  <Icon
                    className="text-muted-foreground size-[18px] shrink-0"
                    aria-hidden="true"
                  />
                  <span>{label}</span>
                  {shortcut ? (
                    <kbd className="bg-muted text-muted-foreground ml-auto rounded-full px-1.5 py-0.5 text-[10px] leading-none font-medium">
                      {shortcut}
                    </kbd>
                  ) : null}
                </button>
              </TooltipTrigger>
              <TooltipContent side="left" sideOffset={10}>
                Открыть: {label.toLocaleLowerCase("ru-RU")}
              </TooltipContent>
            </Tooltip>
          </li>
        ))}
      </ul>
    </nav>
  );
}

export function CanvasWorkspace({
  activeSessionTabId,
  compactChrome = false,
  fileCategory = "all",
  maximized = false,
  projectName,
  mode,
  onClose,
  onFilesBack,
  onMinimize,
  onOpenDesktop,
  onOpenSettings,
  onRetryWorkspaceCatalog,
  onSelectedFileChange,
  onPlacementChange,
  onSessionTabSelect,
  onToolModeChange,
  onToggleMaximize,
  placement = "right",
  selectedFile,
  sessionTabs = [],
  surfaceContent,
  surfaceMode,
  toolMode,
  workspaceFiles = [],
  workspaceCatalogState = "ready",
}: CanvasWorkspaceProps) {
  const sessionTabDomPrefix = useId().replace(/:/g, "");
  const [internalTool, setInternalTool] = useState<ContextPanelMode | null>(
    toolMode ?? null,
  );
  const [internalSelectedFile, setInternalSelectedFile] =
    useState<WorkspaceFile | null>(selectedFile ?? null);
  const activeTool = toolMode === undefined ? internalTool : toolMode;
  const openFile =
    selectedFile === undefined ? internalSelectedFile : selectedFile;
  const setOpenFile = (file: WorkspaceFile | null) => {
    setInternalSelectedFile(file);
    onSelectedFileChange?.(file);
  };
  const setActiveTool = (nextTool: ContextPanelMode | null) => {
    setInternalTool(nextTool);
    onToolModeChange?.(nextTool);
  };
  const resolvedMode = isCanvasMode(mode) ? mode : null;
  const definition = resolvedMode
    ? CANVAS_VIEW_DEFINITIONS[resolvedMode]
    : null;
  const CanvasView = definition?.component;
  const trimmedProjectName = projectName?.trim();
  const projectLabel = trimmedProjectName || "Проект не выбран";

  useEffect(() => {
    if (toolMode !== undefined) {
      setInternalTool(toolMode);
      if (toolMode !== "files") {
        setOpenFile(null);
      }
    }
  }, [toolMode]);

  return (
    <TooltipProvider delayDuration={300}>
      <section
        data-testid="canvas-workspace"
        data-canvas-mode={
          surfaceContent
            ? surfaceMode ?? "surface"
            : openFile
            ? `artifact-${openFile.kind}`
            : activeTool
              ? `tool-${activeTool}`
              : resolvedMode ?? "launcher"
        }
        data-canvas-fullscreen={maximized}
        className={cn(
          "border-border bg-background @container flex h-full min-h-0 min-w-0 flex-col overflow-hidden",
          maximized || compactChrome ? "border-l-0" : "border-l",
        )}
        aria-label="Рабочая область проекта"
      >
        {!compactChrome ? (
        <header className="border-border/80 bg-background flex h-12 shrink-0 items-center gap-2 border-b px-3">
          {onOpenDesktop ? (
            <IconAction
              data-slot="canvas-open-desktop"
              data-canvas-launcher="canvas"
              label={
                surfaceMode === "desktop"
                  ? "Скрыть рабочую область"
                  : "Открыть рабочий стол"
              }
              aria-pressed={surfaceMode === "desktop"}
              className={cn(
                surfaceMode === "desktop" &&
                  "bg-muted text-foreground",
              )}
              onClick={onOpenDesktop}
            >
              <LayoutDashboard aria-hidden="true" />
            </IconAction>
          ) : null}

          <div
            role="tablist"
            aria-label="Открытые рабочие вкладки"
            className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto"
          >
            {sessionTabs.map((tab, tabIndex) => {
              const selected = tab.id === activeSessionTabId;

              return (
                <button
                  key={tab.id}
                  type="button"
                  role="tab"
                  id={`${sessionTabDomPrefix}-tab-${tabIndex}`}
                  aria-controls="canvas-active-tabpanel"
                  aria-selected={selected}
                  tabIndex={selected ? 0 : -1}
                  onClick={() => onSessionTabSelect?.(tab.id)}
                  onKeyDown={(event) => {
                    let nextIndex: number | null = null;
                    if (event.key === "ArrowRight") {
                      nextIndex = (tabIndex + 1) % sessionTabs.length;
                    } else if (event.key === "ArrowLeft") {
                      nextIndex =
                        (tabIndex - 1 + sessionTabs.length) %
                        sessionTabs.length;
                    } else if (event.key === "Home") {
                      nextIndex = 0;
                    } else if (event.key === "End") {
                      nextIndex = sessionTabs.length - 1;
                    }

                    if (nextIndex === null) return;
                    event.preventDefault();
                    const nextTab = sessionTabs[nextIndex];
                    onSessionTabSelect?.(nextTab.id);
                    window.requestAnimationFrame(() => {
                      document
                        .getElementById(
                          `${sessionTabDomPrefix}-tab-${nextIndex}`,
                        )
                        ?.focus();
                    });
                  }}
                  className={cn(
                    "focus-visible:ring-ring/50 h-7 max-w-48 shrink-0 truncate rounded-lg px-2.5 text-[12px] font-medium outline-none focus-visible:ring-[3px]",
                    selected
                      ? "bg-muted text-foreground"
                      : "text-muted-foreground hover:bg-muted/60 hover:text-foreground",
                  )}
                >
                  {tab.title}
                </button>
              );
            })}
          </div>

          <div className="flex shrink-0 items-center gap-1">
            {onToggleMaximize ? (
              <IconAction
                data-slot="canvas-fullscreen-toggle"
                label={maximized ? "Вернуть в панель" : "На весь экран"}
                aria-pressed={maximized}
                onClick={onToggleMaximize}
              >
                {maximized ? (
                  <Minimize2 aria-hidden="true" />
                ) : (
                  <Maximize2 aria-hidden="true" />
                )}
              </IconAction>
            ) : null}
            {onMinimize ? (
              <IconAction
                data-slot="canvas-minimize"
                label="Свернуть в полку задач"
                onClick={onMinimize}
              >
                <Minus aria-hidden="true" />
              </IconAction>
            ) : null}
            {!maximized && onPlacementChange ? (
              <IconAction
                label="Закрепить рабочую область снизу"
                aria-pressed={placement === "bottom"}
                className={cn(
                  placement === "bottom" && "bg-muted/70 text-foreground",
                )}
                onClick={() => onPlacementChange("bottom")}
              >
                <PanelBottom aria-hidden="true" />
              </IconAction>
            ) : null}
            {!maximized && onPlacementChange ? (
              <IconAction
                label="Закрепить рабочую область справа"
                aria-pressed={placement === "right"}
                className={cn(
                  placement === "right" && "bg-muted/70 text-foreground",
                )}
                onClick={() => onPlacementChange("right")}
              >
                <PanelRight aria-hidden="true" />
              </IconAction>
            ) : null}
            {onClose ? (
              <IconAction label="Закрыть рабочую область" onClick={onClose}>
                <X aria-hidden="true" />
              </IconAction>
            ) : null}
          </div>
        </header>
        ) : null}

        <div
          id="canvas-active-tabpanel"
          role="tabpanel"
          aria-labelledby={
            activeSessionTabId
              ? `${sessionTabDomPrefix}-tab-${Math.max(
                  0,
                  sessionTabs.findIndex(
                    (tab) => tab.id === activeSessionTabId,
                  ),
                )}`
              : undefined
          }
          className="flex min-h-0 flex-1 flex-col"
        >
        {surfaceContent ? (
          surfaceContent
        ) : openFile ? (
          <WorkspaceArtifactEditor
            key={openFile.id}
            compactChrome={compactChrome}
            file={openFile}
            projectLabel={projectLabel}
            onBack={() => setOpenFile(null)}
          />
        ) : activeTool === "files" ? (
          <WorkspaceFileManager
            catalogState={workspaceCatalogState}
            files={workspaceFiles}
            initialCategory={fileCategory}
            projectLabel={projectLabel}
            onBack={onFilesBack ?? (() => setActiveTool(null))}
            onOpenFile={setOpenFile}
            onRetry={onRetryWorkspaceCatalog}
          />
        ) : activeTool ? (
          <ContextPanel
            projectName={projectLabel}
            mode={activeTool}
            onClose={() => setActiveTool(null)}
            onOpenSettings={onOpenSettings}
          />
        ) : CanvasView && definition ? (
          <>
            <div className="border-border/80 flex min-h-11 items-center gap-2 border-b px-4">
              <definition.icon
                className="text-muted-foreground size-4"
                aria-hidden="true"
              />
              <span className="text-sm font-medium">{definition.label}</span>
            </div>
            <CanvasView projectLabel={projectLabel} />
          </>
        ) : (
          <WorkspaceLauncher
            onSelect={(nextTool) => {
              setOpenFile(null);
              setActiveTool(nextTool);
            }}
          />
        )}
        </div>
      </section>
    </TooltipProvider>
  );
}
