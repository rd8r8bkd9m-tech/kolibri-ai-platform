"use client";

import { ThreadListItems } from "@/components/assistant-ui/thread-list";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuShortcut,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from "@/components/ui/hover-card";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { WorkspaceFile } from "@/components/kolibri-workspace/workspace-file-manager";
import {
  KOLIBRI_PET_VISIBILITY_EVENT,
  KOLIBRI_PET_VISIBILITY_KEY,
  setKolibriPetVisibility,
} from "@/components/kolibri-shell/kolibri-pet";
import { accountInitials } from "@/lib/identity/contracts";
import { useIdentity } from "@/lib/identity/provider";
import { shouldCloseThreadDrawerForClick } from "@/lib/mobile-thread-navigation";
import { cn } from "@/lib/utils";
import { ThreadListPrimitive } from "@assistant-ui/react";
import {
  ChevronRight,
  Clock3,
  Bot,
  Bird,
  FileText,
  FolderKanban,
  LibraryBig,
  LayoutDashboard,
  PanelLeft,
  LogOut,
  Settings,
  SquarePen,
  UserRound,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useState, type ComponentProps } from "react";

export type WorkspaceProject = {
  id: string;
  name: string;
  updatedAt?: string | null;
};

// The shell never fabricates a project. This collection remains empty until
// projects are supplied by the authenticated product-data API.
export const WORKSPACE_PROJECTS: readonly WorkspaceProject[] = [];

export type WorkspaceSidebarProps = {
  activeDestination?:
    | "chat"
    | "desktop"
    | "projects"
    | "documents"
    | "references";
  className?: string;
  isOverlay?: boolean;
  onOpenChat?: () => void;
  onOpenDocuments?: () => void;
  onOpenDesktop?: () => void;
  onOpenFile?: (file: WorkspaceFile) => void;
  onOpenAiModels?: () => void;
  onOpenProfileSettings?: () => void;
  onOpenProject?: (project: WorkspaceProject) => void;
  onOpenProjects?: () => void;
  onOpenReferenceCatalog?: () => void;
  onRequestClose?: () => void;
  projects?: readonly WorkspaceProject[];
  workspaceFiles?: readonly WorkspaceFile[];
};

export type ProjectContentSection =
  | "all"
  | "documents"
  | "contracts"
  | "estimates"
  | "drawings"
  | "attachments";

const NAVIGATION_ITEMS: readonly {
  id: "desktop" | "projects" | "documents" | "references";
  icon: LucideIcon;
  label: string;
}[] = [
  { id: "desktop", icon: LayoutDashboard, label: "Рабочий стол" },
  { id: "projects", icon: FolderKanban, label: "Проекты" },
  { id: "documents", icon: FileText, label: "Документы" },
  { id: "references", icon: LibraryBig, label: "Справочники" },
] as const;

export function WorkspaceSidebar({
  activeDestination = "chat",
  className,
  isOverlay = false,
  onOpenChat,
  onOpenDocuments,
  onOpenDesktop,
  onOpenFile,
  onOpenAiModels,
  onOpenProfileSettings,
  onOpenProject,
  onOpenProjects,
  onOpenReferenceCatalog,
  onRequestClose,
  projects = WORKSPACE_PROJECTS,
  workspaceFiles = [],
}: WorkspaceSidebarProps) {
  const identity = useIdentity();
  const [petVisible, setPetVisible] = useState(true);
  const [logoutPending, setLogoutPending] = useState(false);
  const [logoutError, setLogoutError] = useState<string | null>(null);

  const logout = async () => {
    setLogoutPending(true);
    setLogoutError(null);
    try {
      await identity.logout();
    } catch (error) {
      setLogoutError(
        error instanceof Error ? error.message : "Не удалось выйти из аккаунта.",
      );
    } finally {
      setLogoutPending(false);
    }
  };

  useEffect(() => {
    try {
      const stored = globalThis.localStorage.getItem(
        KOLIBRI_PET_VISIBILITY_KEY,
      );
      if (stored === "false") setPetVisible(false);
      if (stored === "true") setPetVisible(true);
    } catch {
      // A blocked storage API must not affect navigation.
    }
    const syncVisibility = (event: Event) => {
      const detail = (event as CustomEvent<{ visible?: unknown }>).detail;
      if (typeof detail?.visible === "boolean") {
        setPetVisible(detail.visible);
      }
    };
    globalThis.addEventListener(
      KOLIBRI_PET_VISIBILITY_EVENT,
      syncVisibility,
    );
    return () =>
      globalThis.removeEventListener(
        KOLIBRI_PET_VISIBILITY_EVENT,
        syncVisibility,
      );
  }, []);

  const togglePet = () => {
    setPetVisible((current) => {
      const next = !current;
      setKolibriPetVisibility(next);
      return next;
    });
  };

  return (
    <TooltipProvider delayDuration={420}>
      <aside
        aria-label="Навигация рабочего пространства"
        data-overlay={isOverlay ? "true" : "false"}
        className={cn(
          "text-sidebar-foreground flex h-full min-h-0 w-full min-w-0 flex-col overflow-hidden",
          "border-r border-[#dce5f5] bg-[#f2f6ff] dark:border-sky-950 dark:bg-[#101721]",
          className,
        )}
      >
        <div
          data-slot="workspace-sidebar-chrome"
          className="flex h-12 shrink-0 items-center px-2"
        >
          <SidebarChromeButton
            label="Переключить боковую панель"
            shortcut="⌘B"
            onClick={onRequestClose}
            disabled={!onRequestClose}
          >
            {isOverlay ? (
              <span
                data-slot="mobile-hamburger-icon"
                aria-hidden="true"
                className="flex w-6 flex-col gap-[7px]"
              >
                <span className="h-[2.5px] w-full rounded-full bg-current" />
                <span className="h-[2.5px] w-full rounded-full bg-current" />
              </span>
            ) : (
              <PanelLeft aria-hidden="true" className="size-[18px]" />
            )}
          </SidebarChromeButton>
        </div>

        <div
          data-slot="workspace-sidebar-brand"
          className="flex h-12 shrink-0 items-center pr-2 pl-3.5"
        >
          <div className="flex min-w-0 items-center">
            <span className="truncate text-[17px] font-semibold tracking-[-0.02em]">
              Kolibri
            </span>
          </div>
        </div>

        <div
          data-slot="workspace-sidebar-body"
          className="min-h-0 flex-1 overflow-x-hidden overflow-y-auto px-2.5 pt-1 pb-3"
        >
          <nav aria-label="Основные разделы">
            <ul className="space-y-0.5">
              <li>
                <ThreadListPrimitive.New asChild>
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={onOpenChat}
                    data-slot="workspace-sidebar-destination"
                    className="h-9 w-full justify-start gap-2.5 rounded-lg px-2 text-[14px] font-normal hover:bg-[#e2edff] dark:hover:bg-sky-950/45"
                  >
                    <SquarePen className="size-[17px]" />
                    <span>Новая задача</span>
                  </Button>
                </ThreadListPrimitive.New>
              </li>
              {NAVIGATION_ITEMS.map((item) => (
                <li key={item.label}>
                  <SidebarDestination
                    {...item}
                    active={activeDestination === item.id}
                    previewDisabled={isOverlay}
                    launcherId={
                      item.id === "desktop" ? "sidebar" : undefined
                    }
                    onClick={() => {
                      if (item.id === "desktop") {
                        onOpenDesktop?.();
                        return;
                      }
                      if (item.id === "projects") {
                        onOpenProjects?.();
                        return;
                      }
                      if (item.id === "documents") {
                        onOpenDocuments?.();
                        return;
                      }
                      if (item.id === "references") {
                        onOpenReferenceCatalog?.();
                      }
                    }}
                    onOpenFile={onOpenFile}
                    onOpenProject={onOpenProject}
                    projects={projects}
                    workspaceFiles={workspaceFiles}
                  />
                </li>
              ))}
            </ul>
          </nav>

          <section className="mt-5" aria-labelledby="recent-chats-heading">
            <h2
              id="recent-chats-heading"
              className="text-muted-foreground px-2 pb-1.5 text-sm font-normal"
            >
              Диалоги
            </h2>
            <nav
              aria-label="Диалоги пользователя"
              className="pl-0.5"
              onClickCapture={(event) => {
                const trigger =
                  event.target instanceof Element
                    ? event.target.closest(
                        '[data-slot="aui_thread-list-item-trigger"]',
                      )
                    : null;
                if (
                  shouldCloseThreadDrawerForClick({
                    isThreadTrigger: trigger !== null,
                    longPressConsumed:
                      trigger?.getAttribute(
                        "data-thread-long-press-consumed",
                      ) === "true",
                  })
                ) {
                  onRequestClose?.();
                }
              }}
            >
              <ThreadListItems />
            </nav>
          </section>
        </div>

        <div
          data-slot="workspace-profile-footer"
          className={cn(
            "border-sidebar-border sticky bottom-0 z-20 mt-auto flex min-h-12 shrink-0 items-center border-t px-3 pb-[env(safe-area-inset-bottom)]",
            "bg-[#f2f6ff] dark:bg-[#101721]",
          )}
        >
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                type="button"
                onClick={
                  identity.status === "authenticated"
                    ? undefined
                    : onOpenProfileSettings
                }
                data-slot="workspace-profile-trigger"
                className="focus-visible:ring-sidebar-ring/50 flex min-w-0 flex-1 items-center rounded-lg px-1.5 py-1 text-left outline-none transition-colors hover:bg-[#e2edff] focus-visible:ring-[3px] data-[state=open]:bg-[#dce9fd] dark:hover:bg-sky-950/45"
                aria-label="Открыть меню личного кабинета"
              >
                <span
                  data-slot="workspace-profile-avatar"
                  aria-hidden="true"
                  className="flex size-7 shrink-0 items-center justify-center rounded-full bg-[#fb927c] text-[10px] font-medium text-white"
                >
                  {accountInitials(identity.user)}
                </span>
                <span className="ml-2 flex min-w-0 flex-1 flex-col">
                  <span className="truncate text-sm leading-4 font-medium">
                    {identity.user?.name ??
                      (identity.status === "loading"
                        ? "Загрузка профиля"
                        : "Войти в Kolibri")}
                  </span>
                  <span className="text-muted-foreground truncate text-[10px] leading-3.5">
                    {identity.user
                      ? identity.user.role === "owner"
                        ? "Суперадминистратор"
                        : "Пользователь"
                      : identity.status === "offline"
                        ? "Нет связи"
                        : "Личный кабинет"}
                  </span>
                </span>
                <Settings
                  aria-hidden="true"
                  className="text-muted-foreground size-4 shrink-0"
                />
              </button>
            </DropdownMenuTrigger>
            {identity.status === "authenticated" && identity.user ? (
              <DropdownMenuContent
                side="top"
                align="start"
                sideOffset={8}
                collisionPadding={8}
                className="z-[90] w-[min(20rem,calc(100vw-1rem))] rounded-xl border bg-popover p-1.5 shadow-xl"
              >
                <DropdownMenuLabel className="px-2.5 py-2 font-normal">
                  <span className="flex items-center gap-2.5">
                    <span
                      aria-hidden="true"
                      className="flex size-8 shrink-0 items-center justify-center rounded-full bg-[#fb927c] text-[11px] font-medium text-white"
                    >
                      {accountInitials(identity.user)}
                    </span>
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-medium">
                        {identity.user.name}
                      </span>
                      <span className="text-muted-foreground block truncate text-xs">
                        {identity.user.email}
                      </span>
                    </span>
                  </span>
                </DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  className="rounded-lg px-2.5 py-2 focus:bg-sky-100 dark:focus:bg-sky-950/45"
                  onSelect={onOpenProfileSettings}
                >
                  <UserRound className="size-4" />
                  Личный кабинет
                </DropdownMenuItem>
                <DropdownMenuItem
                  className="rounded-lg px-2.5 py-2 focus:bg-sky-100 dark:focus:bg-sky-950/45"
                  onSelect={onOpenAiModels}
                >
                  <Bot className="size-4" />
                  Подключения моделей
                  <DropdownMenuShortcut>AI</DropdownMenuShortcut>
                </DropdownMenuItem>
                <DropdownMenuItem
                  className="rounded-lg px-2.5 py-2 focus:bg-sky-100 dark:focus:bg-sky-950/45"
                  onSelect={togglePet}
                >
                  <Bird className="size-4" />
                  {petVisible ? "Скрыть питомца" : "Показать питомца"}
                </DropdownMenuItem>
                <DropdownMenuItem
                  className="rounded-lg px-2.5 py-2 focus:bg-sky-100 dark:focus:bg-sky-950/45"
                  onSelect={onOpenProfileSettings}
                >
                  <Settings className="size-4" />
                  Настройки
                  <DropdownMenuShortcut>⌘,</DropdownMenuShortcut>
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  disabled={logoutPending}
                  className="rounded-lg px-2.5 py-2 focus:bg-sky-100 dark:focus:bg-sky-950/45"
                  onSelect={() => void logout()}
                >
                  <LogOut className="size-4" />
                  {logoutPending ? "Выходим…" : "Выйти"}
                </DropdownMenuItem>
                {logoutError ? (
                  <p
                    role="alert"
                    className="px-2.5 py-1.5 text-xs text-destructive"
                  >
                    {logoutError}
                  </p>
                ) : null}
              </DropdownMenuContent>
            ) : null}
          </DropdownMenu>
        </div>
      </aside>
    </TooltipProvider>
  );
}

type SidebarChromeButtonProps = ComponentProps<typeof Button> & {
  label: string;
  shortcut?: string;
};

function SidebarChromeButton({
  children,
  className,
  disabled,
  label,
  shortcut,
  ...props
}: SidebarChromeButtonProps) {
  const button = (
    <Button
      type="button"
      variant="ghost"
      size="icon-sm"
      aria-label={label}
      disabled={disabled}
      className={cn(
        "text-muted-foreground rounded-lg hover:bg-sidebar-accent hover:text-sidebar-foreground",
        className,
      )}
      {...props}
    >
      {children}
    </Button>
  );

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        {disabled ? (
          <span className="inline-flex cursor-default">{button}</span>
        ) : (
          button
        )}
      </TooltipTrigger>
      <TooltipContent
        side="bottom"
        sideOffset={5}
        className="border bg-popover px-2.5 py-1.5 text-[13px] text-popover-foreground shadow-md [&>svg]:hidden"
      >
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

type SidebarDestinationProps = {
  active?: boolean;
  icon: LucideIcon;
  id: "desktop" | "projects" | "documents" | "references";
  label: string;
  launcherId?: string;
  onClick?: () => void;
  onOpenFile?: (file: WorkspaceFile) => void;
  onOpenProject?: (project: WorkspaceProject) => void;
  previewDisabled?: boolean;
  projects: readonly WorkspaceProject[];
  workspaceFiles: readonly WorkspaceFile[];
};

function SidebarDestination({
  active = false,
  icon: Icon,
  id,
  label,
  launcherId,
  onClick,
  onOpenFile,
  onOpenProject,
  previewDisabled = false,
  projects,
  workspaceFiles,
}: SidebarDestinationProps) {
  const destinationButton = (
    <Button
      type="button"
      variant="ghost"
      onClick={onClick}
      data-canvas-launcher={launcherId}
      data-slot="workspace-sidebar-destination"
      aria-current={active ? "page" : undefined}
      className={cn(
        "h-9 w-full justify-start gap-2.5 rounded-lg px-2 text-[14px] font-normal transition-colors hover:bg-[#e2edff] dark:hover:bg-sky-950/45",
        active &&
          "bg-[#d9e7fc] text-sidebar-accent-foreground hover:bg-[#d9e7fc] dark:bg-sky-900/45",
      )}
    >
      <Icon className="size-[17px]" />
      <span className="truncate">{label}</span>
    </Button>
  );

  if (previewDisabled) return destinationButton;

  return (
    <HoverCard>
      <HoverCardTrigger asChild>{destinationButton}</HoverCardTrigger>
      <HoverCardContent
        className="max-h-[min(28rem,calc(100dvh-1rem))] w-[min(21rem,calc(100vw-1rem))] overflow-y-auto overscroll-contain p-3"
      >
        <SidebarDestinationPreview
          id={id}
          label={label}
          onOpenDestination={onClick}
          onOpenFile={onOpenFile}
          onOpenProject={onOpenProject}
          projects={projects}
          workspaceFiles={workspaceFiles}
        />
      </HoverCardContent>
    </HoverCard>
  );
}

const DESTINATION_DESCRIPTIONS = {
  desktop: "Единый холст проекта, инструменты и сохранённые рабочие окна.",
  projects: "Проекты, связанные диалоги и документы в одном контексте.",
  documents: "Все сохранённые сметы, договоры и вложения по проектам.",
  references: "Справочники работ, материалов и региональных цен.",
} as const;

function SidebarDestinationPreview({
  id,
  label,
  onOpenDestination,
  onOpenFile,
  onOpenProject,
  projects,
  workspaceFiles,
}: {
  id: "desktop" | "projects" | "documents" | "references";
  label: string;
  onOpenDestination?: () => void;
  onOpenFile?: (file: WorkspaceFile) => void;
  onOpenProject?: (project: WorkspaceProject) => void;
  projects: readonly WorkspaceProject[];
  workspaceFiles: readonly WorkspaceFile[];
}) {
  const visibleProjects = projects.slice(0, 8);
  const visibleFiles = workspaceFiles.slice(0, 12);

  return (
    <div>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-semibold">{label}</p>
          <p className="text-muted-foreground mt-1 text-xs leading-4">
            {DESTINATION_DESCRIPTIONS[id]}
          </p>
        </div>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          className="size-7 shrink-0 rounded-lg"
          onClick={onOpenDestination}
          aria-label={`Открыть раздел «${label}»`}
        >
          <ChevronRight className="size-4" />
        </Button>
      </div>

      {id === "projects" || id === "desktop" ? (
        <div className="mt-3">
          <p className="text-muted-foreground mb-1.5 px-1 text-[11px] font-medium uppercase tracking-wide">
            Проекты
          </p>
          {visibleProjects.length ? (
            <div className="space-y-1">
              {visibleProjects.map((project) => {
                const files = workspaceFiles
                  .filter((file) => file.projectId === project.id)
                  .slice(0, 3);
                return (
                  <div
                    key={project.id}
                    className="rounded-lg border border-transparent bg-black/[0.025] p-1 dark:bg-white/[0.04]"
                  >
                    <button
                      type="button"
                      onClick={() => onOpenProject?.(project)}
                      className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left outline-none transition-colors hover:bg-sky-100 focus-visible:ring-2 focus-visible:ring-sky-400/45 dark:hover:bg-sky-950/45"
                    >
                      <FolderKanban className="size-4 shrink-0 text-sky-700" />
                      <span className="min-w-0 flex-1 truncate text-xs font-medium">
                        {project.name}
                      </span>
                      <span className="text-muted-foreground text-[10px]">
                        {workspaceFiles.filter(
                          (file) => file.projectId === project.id,
                        ).length}
                      </span>
                    </button>
                    {files.map((file) => (
                      <button
                        key={file.id}
                        type="button"
                        onClick={() => onOpenFile?.(file)}
                        className="text-muted-foreground hover:text-foreground flex w-full items-center gap-2 rounded-md py-1 pr-2 pl-8 text-left text-[11px] outline-none hover:bg-white/80 focus-visible:ring-2 focus-visible:ring-sky-400/45 dark:hover:bg-white/[0.06]"
                      >
                        <FileText className="size-3 shrink-0" />
                        <span className="min-w-0 flex-1 truncate">
                          {file.name}
                        </span>
                      </button>
                    ))}
                  </div>
                );
              })}
            </div>
          ) : (
            <p className="text-muted-foreground rounded-lg bg-black/[0.025] px-2.5 py-2 text-xs dark:bg-white/[0.04]">
              Проекты появятся после первого сохранённого результата.
            </p>
          )}
        </div>
      ) : null}

      {id === "documents" ? (
        <div className="mt-3">
          <p className="text-muted-foreground mb-1.5 px-1 text-[11px] font-medium uppercase tracking-wide">
            Последние файлы
          </p>
          {visibleFiles.length ? (
            <div className="space-y-0.5">
              {visibleFiles.map((file) => (
                <button
                  key={file.id}
                  type="button"
                  onClick={() => onOpenFile?.(file)}
                  className="flex w-full items-start gap-2 rounded-lg px-2 py-2 text-left outline-none transition-colors hover:bg-sky-100 focus-visible:ring-2 focus-visible:ring-sky-400/45 dark:hover:bg-sky-950/45"
                >
                  <FileText className="mt-0.5 size-4 shrink-0 text-sky-700 dark:text-sky-300" />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-xs font-medium">
                      {file.name}
                    </span>
                    <span className="text-muted-foreground mt-0.5 flex items-center gap-1 text-[10px]">
                      <Clock3 className="size-2.5" />
                      {file.projectName || file.status}
                    </span>
                  </span>
                </button>
              ))}
            </div>
          ) : (
            <p className="text-muted-foreground rounded-lg bg-black/[0.025] px-2.5 py-2 text-xs dark:bg-white/[0.04]">
              Сохранённых документов пока нет.
            </p>
          )}
        </div>
      ) : null}
    </div>
  );
}
