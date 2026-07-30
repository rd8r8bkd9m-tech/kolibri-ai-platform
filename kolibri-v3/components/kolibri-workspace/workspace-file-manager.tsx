"use client";

import { useEffect, useMemo, useState } from "react";
import { useAssistantContext } from "@assistant-ui/react";
import {
  AlertCircle,
  ArrowLeft,
  FileArchive,
  FileImage,
  FileSignature,
  FileSpreadsheet,
  FileText,
  Files,
  Folder,
  LayoutGrid,
  List,
  LoaderCircle,
  RefreshCw,
  Search,
  X,
  type LucideIcon,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import type { WorkspaceCatalogLoadState } from "@/lib/workspace-documents";

export type WorkspaceFileKind =
  | "document"
  | "contract"
  | "estimate"
  | "drawing"
  | "attachment";

export type WorkspaceFile = {
  category: Exclude<WorkspaceFileCategory, "all">;
  documentId?: string;
  editable: boolean;
  id: string;
  kind: WorkspaceFileKind;
  modifiedAt: string;
  name: string;
  projectId?: string;
  projectName?: string;
  rowCount?: number;
  size: string;
  status:
    | "Черновик"
    | "На согласовании"
    | "Подписан"
    | "Проверен"
    | "Вложение";
  total?: string;
  version?: number;
};

export type WorkspaceFileCategory =
  | "all"
  | "documents"
  | "contracts"
  | "estimates"
  | "drawings"
  | "attachments";

const FILE_CATEGORIES: readonly {
  id: WorkspaceFileCategory;
  label: string;
  icon: LucideIcon;
}[] = [
  { id: "all", label: "Все файлы", icon: Files },
  { id: "documents", label: "Документы", icon: FileText },
  { id: "contracts", label: "Договоры", icon: FileSignature },
  { id: "estimates", label: "Сметы", icon: FileSpreadsheet },
  { id: "drawings", label: "Чертежи", icon: FileImage },
  { id: "attachments", label: "Вложения", icon: FileArchive },
];

const FILE_KIND_ICON: Record<WorkspaceFileKind, LucideIcon> = {
  document: FileText,
  contract: FileSignature,
  estimate: FileSpreadsheet,
  drawing: FileImage,
  attachment: FileArchive,
};

export function WorkspaceFileManager({
  backLabel = "Назад к инструментам",
  catalogState = "ready",
  initialCategory = "all",
  files = [],
  onBack,
  onOpenFile,
  onRetry,
  projectLabel,
  title = "Файлы",
}: {
  backLabel?: string;
  catalogState?: WorkspaceCatalogLoadState;
  files?: readonly WorkspaceFile[];
  initialCategory?: WorkspaceFileCategory;
  onBack: () => void;
  onOpenFile: (file: WorkspaceFile) => void;
  onRetry?: () => void;
  projectLabel: string;
  title?: string;
}) {
  const [activeCategory, setActiveCategory] =
    useState<WorkspaceFileCategory>(initialCategory);
  const [query, setQuery] = useState("");
  const [view, setView] = useState<"list" | "grid">("list");

  useEffect(() => {
    setActiveCategory(initialCategory);
  }, [initialCategory]);

  useEffect(() => {
    if (globalThis.matchMedia("(max-width: 959px)").matches) {
      setView("grid");
    }
  }, []);

  const categoryCounts = useMemo(
    () =>
      Object.fromEntries(
        FILE_CATEGORIES.map(({ id }) => [
          id,
          id === "all"
            ? files.length
            : files.filter((file) => file.category === id).length,
        ]),
      ) as Record<WorkspaceFileCategory, number>,
    [files],
  );

  const visibleFiles = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase("ru-RU");

    return files.filter((file) => {
      const inCategory =
        activeCategory === "all" || file.category === activeCategory;
      const matchesQuery =
        !normalizedQuery ||
        file.name.toLocaleLowerCase("ru-RU").includes(normalizedQuery);
      return inCategory && matchesQuery;
    });
  }, [activeCategory, files, query]);
  const activeCategoryLabel =
    FILE_CATEGORIES.find(({ id }) => id === activeCategory)?.label ??
    "Все файлы";

  useAssistantContext({
    getContext: () =>
      [
        `Open project file manager: ${projectLabel}.`,
        `Active category: ${activeCategory}.`,
        `Search query: ${query.trim() || "none"}.`,
        `Visible artifacts: ${visibleFiles
          .map((file) => `${file.name} [${file.status}]`)
          .join("; ") || "none"}.`,
      ].join("\n"),
  });

  return (
    <section
      data-slot="workspace-file-manager"
      className="relative flex min-h-0 flex-1 flex-col"
      aria-labelledby="workspace-files-title"
    >
      <header className="border-border/80 hidden h-11 shrink-0 items-center gap-1.5 border-b px-2 min-[960px]:flex">
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              type="button"
              variant="ghost"
              size="icon-xs"
              className="size-7 rounded-lg"
              onClick={onBack}
              aria-label={backLabel}
            >
              <ArrowLeft aria-hidden="true" />
            </Button>
          </TooltipTrigger>
          <TooltipContent side="bottom" sideOffset={6}>
            {backLabel}
          </TooltipContent>
        </Tooltip>

        <Folder
          className="text-muted-foreground ml-1 size-4 shrink-0"
          aria-hidden="true"
        />
        <div className="min-w-0">
          <h2 id="workspace-files-title" className="truncate text-xs font-medium">
            {title}
          </h2>
          <p className="text-muted-foreground truncate text-[10px]">
            {projectLabel}
          </p>
        </div>

        <div className="relative ml-auto hidden w-44 @min-[520px]:block">
          <Search
            className="text-muted-foreground pointer-events-none absolute top-1/2 left-2 size-3.5 -translate-y-1/2"
            aria-hidden="true"
          />
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            className="h-7 rounded-lg pl-7 text-xs shadow-none"
            placeholder="Поиск файлов"
            aria-label="Поиск файлов"
          />
        </div>

        <div className="ml-1 flex items-center">
          <ViewButton
            active={view === "list"}
            label="Список"
            onClick={() => setView("list")}
          >
            <List aria-hidden="true" />
          </ViewButton>
          <ViewButton
            active={view === "grid"}
            label="Сетка"
            onClick={() => setView("grid")}
          >
            <LayoutGrid aria-hidden="true" />
          </ViewButton>
        </div>
      </header>

      {catalogState === "error" && files.length > 0 ? (
        <div
          role="alert"
          className="border-border flex shrink-0 items-center gap-2 border-b px-3 py-2 text-xs"
        >
          <AlertCircle
            className="text-destructive size-4 shrink-0"
            aria-hidden="true"
          />
          <span className="min-w-0 flex-1">
            Не удалось обновить файлы. Показана последняя сохранённая версия.
          </span>
          {onRetry ? (
            <Button type="button" variant="ghost" size="xs" onClick={onRetry}>
              <RefreshCw aria-hidden="true" className="size-3.5" />
              Повторить
            </Button>
          ) : null}
        </div>
      ) : null}

      <div className="grid min-h-0 flex-1 grid-cols-1 @min-[640px]:grid-cols-[168px_minmax(0,1fr)]">
        <aside className="border-border/80 bg-muted/10 hidden min-h-0 border-r px-2 py-3 @min-[640px]:block">
          <nav aria-label="Категории файлов">
            <ul className="space-y-0.5">
              {FILE_CATEGORIES.map(({ id, label, icon: Icon }) => (
                <li key={id}>
                  <button
                    type="button"
                    onClick={() => setActiveCategory(id)}
                    aria-current={activeCategory === id ? "page" : undefined}
                    className={cn(
                      "focus-visible:ring-ring flex h-8 w-full items-center gap-2 rounded-lg px-2 text-left text-xs outline-none focus-visible:ring-2",
                      activeCategory === id
                        ? "bg-muted text-foreground font-medium"
                        : "text-muted-foreground hover:bg-muted/60 hover:text-foreground",
                    )}
                  >
                    <Icon className="size-3.5 shrink-0" aria-hidden="true" />
                    <span className="truncate">{label}</span>
                    <span className="ml-auto text-[10px] tabular-nums">
                      {categoryCounts[id]}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </nav>
        </aside>

        <div className="min-h-0 overflow-auto max-[959px]:pb-24">
          <div
            data-slot="workspace-file-category-tabs"
            className="border-border/80 flex gap-1 overflow-x-auto border-b px-2 py-2 @min-[640px]:hidden"
          >
            {FILE_CATEGORIES.map(({ id, label }) => (
              <Button
                key={id}
                type="button"
                size="xs"
                variant={activeCategory === id ? "secondary" : "ghost"}
                onClick={() => setActiveCategory(id)}
              >
                {label}
                <span className="text-muted-foreground text-[10px]">
                  {categoryCounts[id]}
                </span>
              </Button>
            ))}
          </div>

          {catalogState === "loading" && files.length === 0 ? (
            <CatalogLoading />
          ) : catalogState === "error" && files.length === 0 ? (
            <CatalogError onRetry={onRetry} />
          ) : view === "list" ? (
            <FileList
              activeCategoryLabel={activeCategoryLabel}
              files={visibleFiles}
              hasQuery={query.trim().length > 0}
              onOpenFile={onOpenFile}
              totalFileCount={files.length}
            />
          ) : (
            <FileGrid
              activeCategoryLabel={activeCategoryLabel}
              files={visibleFiles}
              hasQuery={query.trim().length > 0}
              onOpenFile={onOpenFile}
              totalFileCount={files.length}
            />
          )}
        </div>
      </div>

      <div className="absolute inset-x-0 bottom-0 z-10 bg-background px-8 pt-2 pb-[max(2rem,env(safe-area-inset-bottom))] min-[960px]:hidden">
        <div className="relative">
          <Search
            className="text-muted-foreground pointer-events-none absolute top-1/2 left-4 size-6 -translate-y-1/2"
            aria-hidden="true"
          />
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            className="h-12 rounded-full border-foreground/50 bg-muted/45 pr-12 pl-12 text-[17px] shadow-none"
            placeholder="Поиск в библиотеке"
            aria-label="Поиск в библиотеке"
          />
          {query ? (
            <button
              type="button"
              onClick={() => setQuery("")}
              className="focus-visible:ring-ring absolute top-1/2 right-2 grid size-9 -translate-y-1/2 place-items-center rounded-full text-muted-foreground outline-none focus-visible:ring-2"
              aria-label="Очистить поиск в библиотеке"
            >
              <X aria-hidden="true" className="size-5" />
            </button>
          ) : null}
        </div>
      </div>
    </section>
  );
}

function CatalogLoading() {
  return (
    <div role="status" aria-label="Загружаю файлы">
      <div
        data-slot="workspace-file-loading-grid"
        className="grid grid-cols-2 gap-3 px-4 pt-1 min-[960px]:hidden"
      >
        {Array.from({ length: 6 }, (_, index) => (
          <div
            key={index}
            className="h-[10.75rem] animate-pulse rounded-[1.75rem] border border-border bg-muted/55"
          />
        ))}
      </div>
      <div className="text-muted-foreground hidden min-h-56 flex-col items-center justify-center px-5 text-center min-[960px]:flex">
        <LoaderCircle
          className="mb-3 size-5 animate-spin"
          aria-hidden="true"
        />
        <p className="text-foreground text-xs font-medium">Загружаю файлы</p>
        <p className="mt-1 max-w-sm text-[10px] leading-4">
          Kolibri восстанавливает каталог документов проекта.
        </p>
      </div>
    </div>
  );
}

function CatalogError({ onRetry }: { onRetry?: () => void }) {
  return (
    <div
      role="alert"
      className="text-muted-foreground flex min-h-56 flex-col items-center justify-center px-5 text-center"
    >
      <AlertCircle
        className="text-destructive mb-3 size-5"
        aria-hidden="true"
      />
      <p className="text-foreground text-xs font-medium">
        Не удалось загрузить файлы
      </p>
      <p className="mt-1 max-w-sm text-[10px] leading-4">
        Данные не потеряны. Проверьте соединение и повторите загрузку.
      </p>
      {onRetry ? (
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="mt-4"
          onClick={onRetry}
        >
          <RefreshCw aria-hidden="true" className="size-3.5" />
          Повторить
        </Button>
      ) : null}
    </div>
  );
}

function FileList({
  activeCategoryLabel,
  files,
  hasQuery,
  onOpenFile,
  totalFileCount,
}: {
  activeCategoryLabel: string;
  files: readonly WorkspaceFile[];
  hasQuery: boolean;
  onOpenFile: (file: WorkspaceFile) => void;
  totalFileCount: number;
}) {
  if (files.length === 0) {
    return (
      <NoFiles
        activeCategoryLabel={activeCategoryLabel}
        hasQuery={hasQuery}
        totalFileCount={totalFileCount}
      />
    );
  }

  return (
    <div aria-label="Файлы проекта">
      <div
        aria-hidden="true"
        className="border-border/80 text-muted-foreground hidden h-8 grid-cols-[minmax(180px,1fr)_110px_86px_90px] items-center border-b px-3 text-[10px] font-medium @min-[760px]:grid"
      >
        <span>Имя</span>
        <span>Изменён</span>
        <span>Размер</span>
        <span>Статус</span>
      </div>
      {files.map((file) => {
        const Icon = FILE_KIND_ICON[file.kind];

        return (
          <button
            key={file.id}
            type="button"
            aria-label={`Открыть файл «${file.name}»`}
            onClick={() => onOpenFile(file)}
            className="border-border/65 hover:bg-muted/45 focus-visible:bg-muted/45 focus-visible:ring-ring grid min-h-12 w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-3 border-b px-3 text-left outline-none focus-visible:ring-2 focus-visible:ring-inset @min-[760px]:grid-cols-[minmax(180px,1fr)_110px_86px_90px]"
          >
            <span className="flex min-w-0 items-center gap-2.5">
              <span className="bg-muted text-muted-foreground grid size-7 shrink-0 place-items-center rounded-md">
                <Icon className="size-3.5" aria-hidden="true" />
              </span>
              <span className="min-w-0">
                <span className="block truncate text-xs font-medium">
                  {file.name}
                </span>
                <span className="text-muted-foreground mt-0.5 block truncate text-[10px]">
                  {file.projectName
                    ? `${file.projectName} · `
                    : ""}
                  {file.modifiedAt} · {file.size}
                </span>
              </span>
            </span>
            <span
              className="text-muted-foreground hidden text-[10px] @min-[760px]:block"
            >
              {file.modifiedAt}
            </span>
            <span
              className="text-muted-foreground hidden text-[10px] @min-[760px]:block"
            >
              {file.size}
            </span>
            <span className="text-muted-foreground text-[10px]">
              {file.status}
            </span>
          </button>
        );
      })}
    </div>
  );
}

function FileGrid({
  activeCategoryLabel,
  files,
  hasQuery,
  onOpenFile,
  totalFileCount,
}: {
  activeCategoryLabel: string;
  files: readonly WorkspaceFile[];
  hasQuery: boolean;
  onOpenFile: (file: WorkspaceFile) => void;
  totalFileCount: number;
}) {
  if (files.length === 0) {
    return (
      <NoFiles
        activeCategoryLabel={activeCategoryLabel}
        hasQuery={hasQuery}
        totalFileCount={totalFileCount}
      />
    );
  }

  return (
    <ul
      data-slot="workspace-file-grid"
      className="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] gap-2 p-3"
    >
      {files.map((file) => {
        const Icon = FILE_KIND_ICON[file.kind];

        return (
          <li key={file.id}>
            <button
              type="button"
              onClick={() => onOpenFile(file)}
              className="border-border hover:bg-muted/45 focus-visible:ring-ring flex min-h-28 w-full flex-col items-start rounded-xl border p-3 text-left outline-none focus-visible:ring-2"
            >
              <Icon
                data-slot="workspace-file-icon"
                className="text-muted-foreground mb-auto size-5"
                aria-hidden="true"
              />
              <span
                data-slot="workspace-file-name"
                className="mt-4 line-clamp-2 text-xs font-medium"
              >
                {file.name}
              </span>
              {file.projectName ? (
                <span
                  data-slot="workspace-file-project"
                  className="text-muted-foreground mt-1 line-clamp-1 text-[10px]"
                >
                  {file.projectName}
                </span>
              ) : null}
              <span
                data-slot="workspace-file-size"
                className="text-muted-foreground mt-1 text-[10px]"
              >
                {file.size}
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

function NoFiles({
  activeCategoryLabel,
  hasQuery,
  totalFileCount,
}: {
  activeCategoryLabel: string;
  hasQuery: boolean;
  totalFileCount: number;
}) {
  const categoryEmpty = !hasQuery && totalFileCount > 0;
  return (
    <div className="text-muted-foreground flex min-h-64 flex-col items-center justify-center px-5 text-center">
      {hasQuery ? (
        <Search className="mb-3 size-5" aria-hidden="true" />
      ) : (
        <Files className="mb-3 size-5" aria-hidden="true" />
      )}
      <p className="text-foreground text-xs font-medium">
        {hasQuery
          ? "Ничего не найдено"
          : categoryEmpty
            ? `В разделе «${activeCategoryLabel}» пока пусто`
            : "В проекте пока нет файлов"}
      </p>
      <p className="mt-1 max-w-64 text-[10px] leading-relaxed">
        {hasQuery
          ? "Измените категорию или поисковый запрос."
          : categoryEmpty
            ? "Выберите «Все файлы», чтобы увидеть документы из других разделов."
          : "Документы, сметы, договоры и вложения появятся здесь после создания или загрузки."}
      </p>
    </div>
  );
}

function ViewButton({
  active,
  children,
  label,
  onClick,
}: {
  active: boolean;
  children: React.ReactNode;
  label: string;
  onClick: () => void;
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="icon-xs"
          onClick={onClick}
          aria-pressed={active}
          aria-label={label}
          className={cn(
            "size-7 rounded-lg",
            active && "bg-muted text-foreground",
          )}
        >
          {children}
        </Button>
      </TooltipTrigger>
      <TooltipContent side="bottom" sideOffset={6}>
        {label}
      </TooltipContent>
    </Tooltip>
  );
}
