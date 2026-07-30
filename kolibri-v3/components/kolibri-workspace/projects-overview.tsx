"use client";

import { useAssistantContext } from "@assistant-ui/react";
import {
  AlertCircle,
  Folder,
  FolderKanban,
  LoaderCircle,
  RefreshCw,
  Search,
  X,
} from "lucide-react";
import { useMemo, useState } from "react";

import type { WorkspaceProject } from "@/components/kolibri-shell/workspace-sidebar";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { WorkspaceCatalogLoadState } from "@/lib/workspace-documents";
import { cn } from "@/lib/utils";

export type ProjectsOverviewProps = {
  activeProjectId?: string | null;
  catalogState?: WorkspaceCatalogLoadState;
  onOpenProject: (project: WorkspaceProject) => void;
  onRetry?: () => void;
  projects: readonly WorkspaceProject[];
};

export function ProjectsOverview({
  activeProjectId,
  catalogState = "ready",
  onOpenProject,
  onRetry,
  projects,
}: ProjectsOverviewProps) {
  const [query, setQuery] = useState("");
  const [mobileFilter, setMobileFilter] = useState<"all" | "recent">("all");

  const visibleProjects = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase("ru-RU");
    const matchingProjects = projects.filter(
      (project) =>
        !normalizedQuery ||
        project.name.toLocaleLowerCase("ru-RU").includes(normalizedQuery) ||
        project.id.toLocaleLowerCase("ru-RU").includes(normalizedQuery),
    );

    if (mobileFilter !== "recent") return matchingProjects;

    return [...matchingProjects]
      .sort((left, right) => {
        const parseDate = (value?: string | null) => {
          if (!value) return 0;
          const match = value.match(/^(\d{2})\.(\d{2})\.(\d{4})$/);
          if (!match) return 0;
          return Date.UTC(Number(match[3]), Number(match[2]) - 1, Number(match[1]));
        };
        return parseDate(right.updatedAt) - parseDate(left.updatedAt);
      })
      .slice(0, 8);
  }, [mobileFilter, projects, query]);

  const activeProject =
    projects.find((project) => project.id === activeProjectId) ?? null;

  useAssistantContext({
    getContext: () =>
      [
        "Open central surface: Projects.",
        `Search query: ${query.trim() || "none"}.`,
        `Selected project: ${activeProject?.name ?? "none"}.`,
        `Visible projects: ${
          visibleProjects.map((project) => project.name).join("; ") || "none"
        }.`,
      ].join("\n"),
  });

  const emptySearch = projects.length > 0 && visibleProjects.length === 0;

  return (
    <section
      className="bg-background relative flex h-full min-h-0 flex-col"
      aria-labelledby="projects-overview-title"
    >
      <div className="flex min-h-0 flex-1 flex-col min-[960px]:hidden">
        <nav
          aria-label="Фильтры проектов"
          className="flex shrink-0 gap-3 overflow-x-auto px-4 pb-3"
        >
          {[
            { id: "all", label: "Все" },
            { id: "recent", label: "Недавние" },
          ].map((filter) => (
            <button
              key={filter.id}
              type="button"
              aria-pressed={mobileFilter === filter.id}
              onClick={() =>
                setMobileFilter(filter.id as "all" | "recent")
              }
              className={cn(
                "h-11 shrink-0 rounded-full px-4 text-[17px] font-semibold tracking-[-0.02em] outline-none focus-visible:ring-2 focus-visible:ring-ring",
                mobileFilter === filter.id
                  ? "bg-muted text-foreground"
                  : "text-muted-foreground",
              )}
            >
              {filter.label}
            </button>
          ))}
        </nav>

        <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-28">
          {visibleProjects.length > 0 ? (
            <div aria-label="Список проектов" className="space-y-2">
              {visibleProjects.map((project) => (
                <button
                  key={project.id}
                  type="button"
                  aria-current={
                    project.id === activeProjectId ? "page" : undefined
                  }
                  aria-label={`Открыть проект «${project.name}»`}
                  onClick={() => onOpenProject(project)}
                  className="focus-visible:ring-ring flex min-h-[62px] w-full items-center gap-3 rounded-2xl text-left outline-none focus-visible:ring-2"
                >
                  <span className="grid size-[52px] shrink-0 place-items-center rounded-2xl bg-muted">
                    <Folder
                      aria-hidden="true"
                      className="size-6 stroke-[1.75]"
                    />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[18px] leading-6 font-semibold tracking-[-0.025em]">
                      {project.name}
                    </span>
                    <span className="text-muted-foreground mt-0.5 block truncate text-[15px] leading-5">
                      {project.updatedAt?.trim() || "Дата не указана"}
                    </span>
                  </span>
                </button>
              ))}
            </div>
          ) : (
            <div className="text-muted-foreground flex h-full min-h-64 flex-col items-center justify-center px-5 text-center">
              {catalogState === "loading" ? (
                <LoaderCircle
                  className="mb-3 size-6 animate-spin"
                  aria-hidden="true"
                />
              ) : (
                <FolderKanban className="mb-3 size-6" aria-hidden="true" />
              )}
              <p className="text-foreground text-base font-semibold">
                {query.trim() ? "Проекты не найдены" : "Проектов пока нет"}
              </p>
              <p className="mt-1 max-w-xs text-sm leading-5">
                {query.trim()
                  ? "Измените поисковый запрос."
                  : "Новый проект появится после сохранения реальной задачи."}
              </p>
            </div>
          )}
        </div>

        <div className="absolute inset-x-0 bottom-0 z-10 bg-background px-8 pt-2 pb-[max(2rem,env(safe-area-inset-bottom))]">
          <div className="relative">
            <Search
              className="text-muted-foreground pointer-events-none absolute top-1/2 left-4 size-6 -translate-y-1/2"
              aria-hidden="true"
            />
            <Input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              className="h-12 rounded-full border-foreground/50 bg-muted/45 pr-12 pl-12 text-[17px] shadow-none"
              placeholder="Поиск проектов"
              aria-label="Поиск проектов"
            />
            {query ? (
              <button
                type="button"
                onClick={() => setQuery("")}
                className="focus-visible:ring-ring absolute top-1/2 right-2 grid size-9 -translate-y-1/2 place-items-center rounded-full text-muted-foreground outline-none focus-visible:ring-2"
                aria-label="Очистить поиск проектов"
              >
                <X aria-hidden="true" className="size-5" />
              </button>
            ) : null}
          </div>
        </div>
      </div>

      <header className="border-border/80 hidden shrink-0 border-b min-[960px]:block">
        <div className="mx-auto flex min-h-16 w-full max-w-5xl flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center sm:px-6">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <FolderKanban
                className="text-muted-foreground size-4"
                aria-hidden="true"
              />
              <h1
                id="projects-overview-title"
                className="truncate text-sm font-semibold"
              >
                Проекты
              </h1>
            </div>
            <p className="text-muted-foreground mt-0.5 text-[11px]">
              Рабочие папки, документы и связанные задачи
            </p>
          </div>

          <div className="flex min-w-0 flex-1 items-center gap-2 sm:ml-auto sm:max-w-md">
            <div className="relative min-w-0 flex-1">
              <Search
                className="text-muted-foreground pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2"
                aria-hidden="true"
              />
              <Input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                className="h-8 rounded-lg pl-8 text-xs shadow-none"
                placeholder="Найти проект"
                aria-label="Поиск проектов"
                disabled={projects.length === 0}
              />
            </div>
          </div>
        </div>
      </header>

      <div className="hidden min-h-0 flex-1 overflow-auto min-[960px]:block">
        <div className="mx-auto w-full max-w-5xl px-4 py-5 sm:px-6">
          <p className="text-muted-foreground mb-3 text-[11px]">
            {catalogState === "loading" && projects.length === 0
              ? "Загружаю проекты…"
              : catalogState === "error" && projects.length === 0
                ? "Проекты временно недоступны"
                : projects.length === 0
              ? "Проектов пока нет"
              : `${visibleProjects.length} из ${projects.length}`}
          </p>

          {catalogState === "error" && projects.length > 0 ? (
            <div
              role="alert"
              className="border-border mb-3 flex items-center gap-2 rounded-lg border px-3 py-2 text-xs"
            >
              <AlertCircle
                className="text-destructive size-4 shrink-0"
                aria-hidden="true"
              />
              <span className="min-w-0 flex-1">
                Не удалось обновить проекты. Показаны последние данные.
              </span>
              {onRetry ? (
                <Button type="button" variant="ghost" size="xs" onClick={onRetry}>
                  <RefreshCw aria-hidden="true" className="size-3.5" />
                  Повторить
                </Button>
              ) : null}
            </div>
          ) : null}

          <div
            aria-label={
              visibleProjects.length > 0 ? "Список проектов" : undefined
            }
            className="border-border/80 overflow-hidden rounded-xl border"
          >
            {visibleProjects.length > 0 ? (
              <>
                <div
                  aria-hidden="true"
                  className="border-border/80 text-muted-foreground hidden h-8 grid-cols-[minmax(220px,1fr)_minmax(120px,auto)] items-center border-b bg-muted/15 px-3 text-[10px] font-medium md:grid"
                >
                  <span>Проект</span>
                  <span>Обновлён</span>
                </div>

                {visibleProjects.map((project) => {
                  const isSelected = project.id === activeProjectId;

                  return (
                    <button
                      key={project.id}
                      type="button"
                      aria-current={isSelected ? "page" : undefined}
                      aria-label={`Открыть проект «${project.name}»`}
                      onClick={() => onOpenProject(project)}
                      className={cn(
                        "border-border/65 focus-visible:ring-ring grid min-h-14 w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-3 border-b px-3 text-left outline-none transition-colors last:border-b-0 focus-visible:ring-2 focus-visible:ring-inset",
                        isSelected
                          ? "bg-muted/70"
                          : "hover:bg-muted/40 focus-visible:bg-muted/40",
                      )}
                    >
                      <span
                        className="flex min-w-0 items-center gap-3"
                      >
                        <span
                          className={cn(
                            "grid size-8 shrink-0 place-items-center rounded-lg",
                            isSelected
                              ? "bg-background text-foreground"
                              : "bg-muted text-muted-foreground",
                          )}
                        >
                          <FolderKanban
                            className="size-4"
                            aria-hidden="true"
                          />
                        </span>
                        <span className="min-w-0">
                          <span className="block truncate text-xs font-medium">
                            {project.name}
                          </span>
                          <span className="text-muted-foreground mt-0.5 block truncate text-[10px]">
                            {isSelected ? "Открыт · " : ""}
                            Проект …{project.id.slice(-8)}
                          </span>
                        </span>
                      </span>
                      <span
                        className="text-muted-foreground text-[10px]"
                      >
                        {project.updatedAt?.trim() || "—"}
                      </span>
                    </button>
                  );
                })}
              </>
            ) : (
              <div className="text-muted-foreground flex min-h-56 flex-col items-center justify-center px-5 text-center">
                {catalogState === "loading" ? (
                  <LoaderCircle
                    className="mb-3 size-5 animate-spin"
                    aria-hidden="true"
                  />
                ) : catalogState === "error" ? (
                  <AlertCircle
                    className="text-destructive mb-3 size-5"
                    aria-hidden="true"
                  />
                ) : emptySearch ? (
                  <Search className="mb-3 size-5" aria-hidden="true" />
                ) : (
                  <FolderKanban className="mb-3 size-5" aria-hidden="true" />
                )}
                <p className="text-foreground text-xs font-medium">
                  {catalogState === "loading"
                    ? "Загружаю проекты"
                    : catalogState === "error"
                      ? "Не удалось загрузить проекты"
                      : emptySearch
                        ? "Проекты не найдены"
                        : "Проектов пока нет"}
                </p>
                <p className="mt-1 max-w-sm text-[10px] leading-4">
                  {catalogState === "loading"
                    ? "Подождите, пока Kolibri восстановит список."
                    : catalogState === "error"
                      ? "Проверьте соединение и повторите загрузку."
                      : emptySearch
                    ? "Измените запрос и попробуйте снова."
                    : "Опишите первую задачу в чате. Проект появится здесь после сохранения сервером."}
                </p>
                {catalogState === "error" && onRetry ? (
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
            )}
          </div>

        </div>
      </div>
    </section>
  );
}
