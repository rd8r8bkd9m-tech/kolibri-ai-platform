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
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { ThreadListPrimitive } from "@assistant-ui/react";
import {
  Check,
  ChevronDown,
  Folder,
  FolderOpen,
  LayoutDashboard,
  PanelLeft,
  SquarePen,
} from "lucide-react";
import type { WorkspaceProject } from "./workspace-sidebar";

export type WorkspaceHeaderProps = {
  activeProjectId?: string | null;
  canvasOpen: boolean;
  className?: string;
  navigationOpen: boolean;
  onNavigationPreviewEnter?: () => void;
  onNavigationPreviewLeave?: () => void;
  onOpenDesktop: () => void;
  onProjectSelect?: (project: WorkspaceProject) => void;
  onToggleNavigation: () => void;
  projectName?: string;
  projects?: readonly WorkspaceProject[];
  threadTitle?: string;
};

export function WorkspaceHeader({
  activeProjectId,
  canvasOpen,
  className,
  navigationOpen,
  onNavigationPreviewEnter,
  onNavigationPreviewLeave,
  onOpenDesktop,
  onProjectSelect,
  onToggleNavigation,
  projectName,
  projects = [],
  threadTitle = "Новая задача",
}: WorkspaceHeaderProps) {
  const projectLabel = projectName?.trim() || null;

  return (
    <TooltipProvider delayDuration={350}>
      <header
        className={cn(
          "bg-background @container flex h-12 shrink-0 items-center gap-1.5 border-b px-3",
          className,
        )}
      >
        {!navigationOpen ? (
          <>
            <HeaderIconButton
              label="Переключить боковую панель"
              shortcut="⌘B"
              aria-controls="workspace-project-navigation"
              aria-expanded={false}
              onClick={onToggleNavigation}
              onMouseEnter={onNavigationPreviewEnter}
              onMouseLeave={onNavigationPreviewLeave}
              className="relative"
            >
              <PanelLeft aria-hidden="true" />
              <span
                aria-hidden="true"
                className="absolute top-0.5 right-0.5 size-1.5 rounded-full bg-[#339cff]"
              />
            </HeaderIconButton>
            <HeaderNewThreadButton />
            <span
              aria-hidden="true"
              className="bg-border mx-1 h-6 w-px shrink-0"
            />
          </>
        ) : null}

        <Folder
          className="text-muted-foreground ml-0.5 size-[17px] shrink-0"
          aria-hidden="true"
        />
        <p className="min-w-0 truncate text-[15px] font-semibold tracking-[-0.01em]">
          {threadTitle}
        </p>

        <div className="ml-auto flex shrink-0 items-center gap-1">
          <DropdownMenu>
            <Tooltip>
              <TooltipTrigger asChild>
                <DropdownMenuTrigger asChild>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="h-7 max-w-44 gap-1.5 rounded-[10px] px-2.5 shadow-none"
                    aria-label={
                      projectLabel
                        ? `Выбрать проект. Текущий проект: ${projectLabel}`
                        : "Выбрать проект"
                    }
                    disabled={projects.length === 0}
                  >
                    <FolderOpen className="size-4 shrink-0" aria-hidden="true" />
                    {projectLabel ? (
                      <span className="hidden min-w-0 truncate text-xs @min-[720px]:inline">
                        {projectLabel}
                      </span>
                    ) : (
                      <span className="hidden min-w-0 truncate text-xs text-muted-foreground @min-[720px]:inline">
                        Проект не выбран
                      </span>
                    )}
                    <ChevronDown
                      className="text-muted-foreground size-3.5 shrink-0"
                      aria-hidden="true"
                    />
                  </Button>
                </DropdownMenuTrigger>
              </TooltipTrigger>
              <TooltipContent side="bottom" sideOffset={8}>
                {projects.length === 0
                  ? "Проекты появятся после сохранения"
                  : projectLabel
                    ? `Проект: ${projectLabel}`
                    : "Выбрать проект"}
              </TooltipContent>
            </Tooltip>
            <DropdownMenuContent align="end" className="w-72">
              <DropdownMenuLabel className="text-xs">
                Текущий проект
              </DropdownMenuLabel>
              <DropdownMenuSeparator />
              {projects.map((project) => {
                const active = project.id === activeProjectId;
                return (
                  <DropdownMenuItem
                    key={project.id}
                    onSelect={() => onProjectSelect?.(project)}
                    className="min-h-10"
                  >
                    <FolderOpen aria-hidden="true" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-xs font-medium">
                        {project.name}
                      </span>
                      <span className="text-muted-foreground block truncate text-[10px]">
                        {project.updatedAt?.trim() || `…${project.id.slice(-8)}`}
                      </span>
                    </span>
                    {active ? <Check aria-hidden="true" /> : null}
                  </DropdownMenuItem>
                );
              })}
            </DropdownMenuContent>
          </DropdownMenu>

          <HeaderIconButton
            label={
              canvasOpen
                ? "Скрыть рабочую область"
                : "Открыть рабочий стол"
            }
            data-canvas-launcher="header"
            aria-controls="workspace-canvas"
            aria-expanded={canvasOpen}
            aria-pressed={canvasOpen}
            className={cn(
              canvasOpen && "bg-muted text-foreground",
            )}
            onClick={onOpenDesktop}
          >
            <LayoutDashboard aria-hidden="true" />
          </HeaderIconButton>
        </div>
      </header>
    </TooltipProvider>
  );
}

function HeaderNewThreadButton() {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <ThreadListPrimitive.New asChild>
          <Button
            type="button"
            variant="ghost"
            size="icon-xs"
            className="text-muted-foreground hover:text-foreground size-7 rounded-lg"
            aria-label="Новая задача"
          >
            <SquarePen aria-hidden="true" />
          </Button>
        </ThreadListPrimitive.New>
      </TooltipTrigger>
      <TooltipContent side="bottom" sideOffset={8}>
        Новая задача
      </TooltipContent>
    </Tooltip>
  );
}

type HeaderIconButtonProps = React.ComponentProps<typeof Button> & {
  label: string;
  shortcut?: string;
};

function HeaderIconButton({
  children,
  className,
  label,
  shortcut,
  ...props
}: HeaderIconButtonProps) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="icon-xs"
          className={cn(
            "text-muted-foreground hover:text-foreground size-7 rounded-lg",
            className,
          )}
          {...props}
        >
          {children}
          <span className="sr-only">{label}</span>
        </Button>
      </TooltipTrigger>
      <TooltipContent side="bottom" sideOffset={8}>
        <span className="flex items-center gap-3">
          <span>{label}</span>
          {shortcut ? (
            <kbd className="bg-muted text-muted-foreground rounded px-1.5 py-0.5 font-sans text-[11px] leading-none">
              {shortcut}
            </kbd>
          ) : null}
        </span>
      </TooltipContent>
    </Tooltip>
  );
}
