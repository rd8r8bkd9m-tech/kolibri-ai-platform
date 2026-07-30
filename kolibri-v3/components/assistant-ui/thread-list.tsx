"use client";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from "@/components/ui/hover-card";
import {
  canStartThreadLongPress,
  shouldIgnoreThreadMenuCloseRequest,
  THREAD_LONG_PRESS_CLICK_SUPPRESSION_MS,
  THREAD_LONG_PRESS_DURATION_MS,
  THREAD_LONG_PRESS_MOVE_TOLERANCE_PX,
} from "@/lib/mobile-thread-navigation";
import { cn } from "@/lib/utils";
import {
  AuiIf,
  ThreadListItemMorePrimitive,
  ThreadListItemPrimitive,
  ThreadListPrimitive,
  useAui,
  useAuiState,
} from "@assistant-ui/react";
import {
  ArchiveIcon,
  ArchiveRestoreIcon,
  Clock3Icon,
  FolderKanbanIcon,
  MoreHorizontalIcon,
  PinIcon,
  PinOffIcon,
  PlusIcon,
  SearchIcon,
  Trash2Icon,
} from "lucide-react";
import {
  forwardRef,
  Fragment,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
  type ComponentPropsWithoutRef,
  type FC,
} from "react";

const COMPACT_THREAD_MENU_QUERY = "(max-width: 959px)";

function subscribeCompactThreadMenu(listener: () => void) {
  const media = window.matchMedia(COMPACT_THREAD_MENU_QUERY);
  media.addEventListener("change", listener);
  return () => media.removeEventListener("change", listener);
}

function compactThreadMenuSnapshot() {
  return window.matchMedia(COMPACT_THREAD_MENU_QUERY).matches;
}

function serverCompactThreadMenuSnapshot() {
  return false;
}

export const ThreadList: FC = () => {
  const [search, setSearch] = useState("");
  const hasThreads = useAuiState((s) => s.threads.threadIds.length > 0);

  return (
    <ThreadListRoot>
      <ThreadListNew />
      {hasThreads && (
        <ThreadListSearch value={search} onValueChange={setSearch} />
      )}
      <ThreadListItems searchQuery={hasThreads ? search : ""} />
    </ThreadListRoot>
  );
};

export const ThreadListSearch = forwardRef<
  HTMLInputElement,
  Omit<ComponentPropsWithoutRef<typeof Input>, "value" | "onChange"> & {
    value: string;
    onValueChange: (value: string) => void;
  }
>(({ className, value, onValueChange, ...props }, ref) => {
  return (
    <div data-slot="aui_thread-list-search" className="relative px-0.5 py-1">
      <SearchIcon
        data-slot="aui_thread-list-search-icon"
        className="text-muted-foreground pointer-events-none absolute start-3 top-1/2 size-4 -translate-y-1/2"
      />
      <Input
        ref={ref}
        type="search"
        value={value}
        onChange={(event) => onValueChange(event.target.value)}
        aria-label="Поиск по задачам"
        placeholder="Поиск"
        className={cn(
          "h-9 rounded-lg border-transparent bg-black/[0.035] ps-8 text-sm shadow-none focus-visible:border-ring/40 dark:bg-white/[0.055]",
          className,
        )}
        {...props}
      />
    </div>
  );
});

ThreadListSearch.displayName = "ThreadListSearch";

export const ThreadListRoot: FC<
  ComponentPropsWithoutRef<typeof ThreadListPrimitive.Root>
> = ({ className, ...props }) => {
  return (
    <ThreadListPrimitive.Root
      data-slot="aui_thread-list-root"
      className={cn("flex flex-col gap-0.5", className)}
      {...props}
    />
  );
};

export const ThreadListItems: FC<
  ComponentPropsWithoutRef<"div"> & { searchQuery?: string }
> = ({ className, searchQuery = "", ...props }) => {
  return (
    <div
      data-slot="aui_thread-list-items"
      className={cn("flex flex-col gap-0.5", className)}
      {...props}
    >
      <AuiIf condition={(s) => s.threads.isLoading}>
        <ThreadListSkeleton />
      </AuiIf>
      <AuiIf condition={(s) => !s.threads.isLoading}>
        <ThreadListItemGroups searchQuery={searchQuery} />
        <ArchivedThreadListItems searchQuery={searchQuery} />
      </AuiIf>
    </div>
  );
};

const DAY_IN_MS = 86_400_000;

const dateGroupLabel = (
  date: Date | undefined,
  startOfToday: number,
): string => {
  if (!date || date.getTime() >= startOfToday) return "Сегодня";
  if (date.getTime() >= startOfToday - DAY_IN_MS) return "Вчера";
  return "Ранее";
};

type ThreadListGroup = { label: string; indices: number[] };

const ThreadListItemGroups: FC<{ searchQuery?: string }> = ({
  searchQuery = "",
}) => {
  const threadIds = useAuiState((s) => s.threads.threadIds);
  const threadItems = useAuiState((s) => s.threads.threadItems);

  const query = searchQuery.trim().toLowerCase();

  const { filteredIndices, groups } = useMemo(() => {
    const itemsById = new Map(threadItems.map((item) => [item.id, item]));
    const dates = threadIds.map((id) => itemsById.get(id)?.lastMessageAt);
    const filteredIndices = threadIds
      .map((id, index) => ({ id, index }))
      .filter(
        ({ id }) =>
          !query ||
          (itemsById.get(id)?.title || "Новая задача")
            .toLowerCase()
            .includes(query),
      )
      .map(({ index }) => index);
    if (!filteredIndices.some((index) => dates[index])) {
      return { filteredIndices, groups: null };
    }

    const now = new Date();
    const startOfToday = new Date(
      now.getFullYear(),
      now.getMonth(),
      now.getDate(),
    ).getTime();
    const time = (index: number) =>
      dates[index]?.getTime() ?? Number.MAX_SAFE_INTEGER;
    const sorted = [...filteredIndices].sort((a, b) => time(b) - time(a));

    const pinned = sorted.filter(
      (index) => itemsById.get(threadIds[index]!)?.custom?.pinned === true,
    );
    const unpinned = sorted.filter(
      (index) => itemsById.get(threadIds[index]!)?.custom?.pinned !== true,
    );
    const result: ThreadListGroup[] = pinned.length
      ? [{ label: "Закреплённые", indices: pinned }]
      : [];
    for (const index of unpinned) {
      const label = dateGroupLabel(dates[index], startOfToday);
      const lastGroup = result[result.length - 1];
      if (lastGroup?.label === label) {
        lastGroup.indices.push(index);
      } else {
        result.push({ label, indices: [index] });
      }
    }
    return { filteredIndices, groups: result };
  }, [threadIds, threadItems, query]);

  if (query && filteredIndices.length === 0) {
    return (
      <div
        data-slot="aui_thread-list-empty"
        className="text-muted-foreground px-2.5 py-4 text-sm"
      >
        Ничего не найдено
      </div>
    );
  }

  if (!groups) {
    return filteredIndices.map((index) => (
      <ThreadListPrimitive.ItemByIndex
        key={threadIds[index]}
        index={index}
        components={{ ThreadListItem }}
      />
    ));
  }

  return groups.map((group) => (
    <Fragment key={group.label}>
      <div
        data-slot="aui_thread-list-group-label"
        className="text-muted-foreground px-2.5 pt-3 pb-1 text-xs font-medium"
      >
        {group.label}
      </div>
      {group.indices.map((index) => (
        <ThreadListPrimitive.ItemByIndex
          key={threadIds[index]}
          index={index}
          components={{ ThreadListItem }}
        />
      ))}
    </Fragment>
  ));
};

const ArchivedThreadListItems: FC<{ searchQuery?: string }> = ({
  searchQuery = "",
}) => {
  const archivedThreadIds = useAuiState((s) => s.threads.archivedThreadIds);
  const threadItems = useAuiState((s) => s.threads.threadItems);
  const query = searchQuery.trim().toLowerCase();
  const visibleIndices = useMemo(() => {
    const itemsById = new Map(threadItems.map((item) => [item.id, item]));
    return archivedThreadIds
      .map((id, index) => ({ id, index }))
      .filter(
        ({ id }) =>
          !query ||
          (itemsById.get(id)?.title || "Новая задача")
            .toLowerCase()
            .includes(query),
      )
      .map(({ index }) => index);
  }, [archivedThreadIds, query, threadItems]);

  if (visibleIndices.length === 0) return null;

  return (
    <details
      data-slot="aui_thread-list-archive"
      className="group/archive mt-2"
      open={query ? true : undefined}
    >
      <summary className="text-muted-foreground hover:bg-sky-100/70 flex h-8 cursor-pointer list-none items-center rounded-lg px-2.5 text-xs font-medium outline-none transition-colors focus-visible:ring-2 focus-visible:ring-sky-400/45 dark:hover:bg-sky-950/35">
        <ArchiveIcon className="mr-2 size-3.5" />
        <span className="flex-1">Архив</span>
        <span className="rounded-full bg-black/[0.045] px-1.5 py-0.5 text-[10px] dark:bg-white/[0.08]">
          {visibleIndices.length}
        </span>
      </summary>
      <div className="mt-0.5 flex flex-col gap-0.5">
        {visibleIndices.map((index) => (
          <ThreadListPrimitive.ItemByIndex
            key={archivedThreadIds[index]}
            index={index}
            archived
            components={{ ThreadListItem }}
          />
        ))}
      </div>
    </details>
  );
};

export const ThreadListNew = forwardRef<
  HTMLButtonElement,
  ComponentPropsWithoutRef<typeof Button> & { labelClassName?: string }
>(({ className, labelClassName, children, ...props }, ref) => {
  return (
    <ThreadListPrimitive.New asChild>
      <Button
        ref={ref}
        variant="ghost"
        data-slot="aui_thread-list-new"
        className={cn(
            "h-10 justify-start gap-2 rounded-xl bg-foreground px-3 text-sm font-medium text-background shadow-sm hover:bg-foreground/88 data-active:bg-foreground",
          className,
        )}
        {...props}
      >
        {children ?? (
          <>
            <PlusIcon
              data-slot="aui_thread-list-new-icon"
              className="size-4 shrink-0"
            />
            <span
              data-slot="aui_thread-list-new-label"
              className={cn("whitespace-nowrap", labelClassName)}
            >
              Новая задача
            </span>
          </>
        )}
      </Button>
    </ThreadListPrimitive.New>
  );
});

ThreadListNew.displayName = "ThreadListNew";

const ThreadListSkeleton: FC = () => {
  return (
    <div className="flex flex-col gap-0.5">
      {Array.from({ length: 5 }, (_, i) => (
        <div
          key={i}
          role="status"
          aria-label="Загрузка задач"
          data-slot="aui_thread-list-skeleton-wrapper"
          className="flex h-9 items-center px-2.5"
        >
          <Skeleton
            data-slot="aui_thread-list-skeleton"
            className="h-3.5 w-full"
          />
        </div>
      ))}
    </div>
  );
};

export const ThreadListItem: FC = () => {
  const aui = useAui();
  const [menuOpen, setMenuOpen] = useState(false);
  const [longPressing, setLongPressing] = useState(false);
  const compactThreadMenu = useSyncExternalStore(
    subscribeCompactThreadMenu,
    compactThreadMenuSnapshot,
    serverCompactThreadMenuSnapshot,
  );
  const longPressRef = useRef<{
    timer: ReturnType<typeof setTimeout>;
    x: number;
    y: number;
  } | null>(null);
  const threadTriggerRef = useRef<HTMLButtonElement | null>(null);
  const suppressNextClickRef = useRef(false);
  const suppressClickResetTimerRef = useRef<ReturnType<
    typeof setTimeout
  > | null>(null);
  const title = useAuiState(
    (state) => state.threadListItem.title || "Новая задача",
  );
  const status = useAuiState((state) => state.threadListItem.status);
  const lastMessageAt = useAuiState(
    (state) => state.threadListItem.lastMessageAt,
  );
  const custom = useAuiState((state) => state.threadListItem.custom);
  const isPinned = custom?.pinned === true;
  const isDraft = custom?.draft === true;
  const projectId =
    typeof custom?.projectId === "string" ? custom.projectId : null;
  const lastActivity = lastMessageAt
    ? new Intl.DateTimeFormat("ru-RU", {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(lastMessageAt)
    : "Сообщений пока нет";
  const cancelLongPress = () => {
    setLongPressing(false);
    if (longPressRef.current) {
      clearTimeout(longPressRef.current.timer);
      longPressRef.current = null;
    }
  };
  const clearConsumedLongPress = () => {
    suppressNextClickRef.current = false;
    if (suppressClickResetTimerRef.current) {
      clearTimeout(suppressClickResetTimerRef.current);
      suppressClickResetTimerRef.current = null;
    }
    threadTriggerRef.current?.removeAttribute(
      "data-thread-long-press-consumed",
    );
  };
  const handleMenuOpenChange = (open: boolean) => {
    if (
      shouldIgnoreThreadMenuCloseRequest({
        open,
        longPressClickPending: suppressNextClickRef.current,
      })
    ) {
      return;
    }
    setMenuOpen(open);
    if (!open) clearConsumedLongPress();
  };
  const consumeLongPressClick = (event: {
    preventDefault: () => void;
    stopPropagation: () => void;
  }) => {
    if (!suppressNextClickRef.current) return;
    event.preventDefault();
    event.stopPropagation();
    clearConsumedLongPress();
  };
  const preventConsumedLongPressNavigation = (event: {
    preventDefault: () => void;
  }) => {
    if (suppressNextClickRef.current) event.preventDefault();
  };

  useEffect(
    () => () => {
      if (longPressRef.current) {
        clearTimeout(longPressRef.current.timer);
      }
      if (suppressClickResetTimerRef.current) {
        clearTimeout(suppressClickResetTimerRef.current);
      }
      threadTriggerRef.current?.removeAttribute(
        "data-thread-long-press-consumed",
      );
    },
    [],
  );

  const threadMenuItemClass = cn(
    "flex cursor-default select-none items-center gap-2 rounded-lg px-2.5 py-2 outline-none data-[highlighted]:bg-sky-100 dark:data-[highlighted]:bg-sky-950/50",
    compactThreadMenu && "min-h-12 rounded-xl px-3 text-[16px]",
  );

  return (
    <ThreadListItemPrimitive.Root
      data-slot="aui_thread-list-item"
      data-long-pressing={longPressing ? "true" : undefined}
      data-thread-action-menu-open={menuOpen ? "true" : undefined}
      className="group relative flex min-h-9 items-center rounded-lg transition-[transform,background-color] duration-150 hover:bg-[#e2edff] focus-within:bg-[#e2edff] focus-visible:bg-[#e2edff] data-active:bg-[#d8e6fb] data-[long-pressing=true]:scale-[0.985] data-[long-pressing=true]:bg-[#dce9fd] has-data-[state=open]:bg-[#dce9fd] dark:hover:bg-sky-950/45 dark:focus-within:bg-sky-950/45 dark:data-active:bg-sky-900/45 dark:data-[long-pressing=true]:bg-sky-900/45"
    >
      <HoverCard>
        <HoverCardTrigger asChild>
          <ThreadListItemPrimitive.Trigger
            ref={threadTriggerRef}
            data-slot="aui_thread-list-item-trigger"
            className="flex h-full min-w-0 flex-1 items-center rounded-lg px-2.5 text-start text-[13px] outline-none group-hover:pe-9 group-focus-within:pe-9 group-has-data-[state=open]:pe-9 group-data-active:pe-9 focus-visible:ring-2 focus-visible:ring-ring/50"
            aria-label={`Открыть задачу «${title}»`}
            onPointerDown={(event) => {
              if (
                !canStartThreadLongPress({
                  isDraft,
                  pointerType: event.pointerType,
                })
              ) {
                return;
              }
              cancelLongPress();
              setLongPressing(true);
              const trigger = event.currentTarget;
              longPressRef.current = {
                x: event.clientX,
                y: event.clientY,
                timer: setTimeout(() => {
                  setLongPressing(false);
                  suppressNextClickRef.current = true;
                  trigger.setAttribute(
                    "data-thread-long-press-consumed",
                    "true",
                  );
                  suppressClickResetTimerRef.current = setTimeout(
                    clearConsumedLongPress,
                    THREAD_LONG_PRESS_CLICK_SUPPRESSION_MS,
                  );
                  longPressRef.current = null;
                  globalThis.navigator.vibrate?.(10);
                  setMenuOpen(true);
                }, THREAD_LONG_PRESS_DURATION_MS),
              };
            }}
            onPointerMove={(event) => {
              const pending = longPressRef.current;
              if (
                pending &&
                Math.hypot(
                  event.clientX - pending.x,
                  event.clientY - pending.y,
                ) > THREAD_LONG_PRESS_MOVE_TOLERANCE_PX
              ) {
                cancelLongPress();
              }
            }}
            onPointerUp={cancelLongPress}
            onPointerCancel={cancelLongPress}
            onPointerLeave={cancelLongPress}
            onContextMenu={(event) => {
              if (isDraft) {
                event.preventDefault();
                return;
              }
              event.preventDefault();
              cancelLongPress();
              setMenuOpen(true);
            }}
            onClickCapture={preventConsumedLongPressNavigation}
            onClick={consumeLongPressClick}
          >
            <span
              data-slot="aui_thread-list-item-title"
              className="min-w-0 flex-1 truncate"
            >
              <ThreadListItemPrimitive.Title fallback="Новая задача" />
            </span>
          </ThreadListItemPrimitive.Trigger>
        </HoverCardTrigger>
        <HoverCardContent className="max-h-[min(22rem,calc(100dvh-1rem))] w-[min(20rem,calc(100vw-1rem))] overflow-y-auto overscroll-contain p-3">
          <div className="flex items-start gap-2.5">
            <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-sky-100 text-sky-700 dark:bg-sky-950 dark:text-sky-300">
              <FolderKanbanIcon className="size-4" />
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-1.5">
                <p className="line-clamp-2 text-sm leading-5 font-medium">
                  {title}
                </p>
                {isPinned ? (
                  <PinIcon className="size-3.5 shrink-0 text-sky-600" />
                ) : null}
              </div>
              <p className="text-muted-foreground mt-0.5 text-xs">
                {status === "archived" ? "Диалог в архиве" : "Диалог проекта"}
              </p>
            </div>
          </div>
          <div className="mt-3 space-y-2 rounded-lg bg-black/[0.025] p-2.5 text-xs dark:bg-white/[0.045]">
            <div className="text-muted-foreground flex items-start gap-2">
              <Clock3Icon className="mt-0.5 size-3.5 shrink-0" />
              <span>{lastActivity}</span>
            </div>
            {projectId ? (
              <div className="text-muted-foreground flex items-start gap-2">
                <FolderKanbanIcon className="mt-0.5 size-3.5 shrink-0" />
                <span className="min-w-0 break-all">
                  Проект · {projectId}
                </span>
              </div>
            ) : null}
          </div>
          <Button
            type="button"
            size="sm"
            variant="secondary"
            className="mt-3 h-8 w-full justify-center rounded-lg"
            onClick={() => {
              if (status === "archived") {
                aui.threadListItem.unarchive();
                return;
              }
              aui.threadListItem.switchTo();
            }}
          >
            {status === "archived" ? "Вернуть из архива" : "Открыть диалог"}
          </Button>
        </HoverCardContent>
      </HoverCard>

      {!isDraft ? (
        <ThreadListItemMorePrimitive.Root
          sharedFocusGroup
          open={menuOpen}
          onOpenChange={handleMenuOpenChange}
        >
          <ThreadListItemMorePrimitive.Trigger
            aria-label={`Действия с диалогом «${title}»`}
            render={
              <button
                type="button"
                className="absolute end-1 top-1/2 flex size-7 -translate-y-1/2 items-center justify-center rounded-md text-muted-foreground opacity-0 outline-none transition hover:bg-white/70 hover:text-foreground focus-visible:ring-2 focus-visible:ring-sky-400/50 group-hover:opacity-100 group-focus-within:opacity-100 group-data-active:opacity-100 data-[state=open]:bg-white/70 data-[state=open]:opacity-100 dark:hover:bg-white/10"
              />
            }
          >
            <MoreHorizontalIcon className="size-4" />
          </ThreadListItemMorePrimitive.Trigger>
          <ThreadListItemMorePrimitive.Content
            align={compactThreadMenu ? "center" : "start"}
            side={compactThreadMenu ? "bottom" : "right"}
            sideOffset={compactThreadMenu ? 10 : 6}
            collisionPadding={8}
            className={cn(
              "z-[90] min-w-52 rounded-xl border bg-popover p-1.5 text-sm text-popover-foreground shadow-xl outline-none",
              compactThreadMenu &&
                "w-[min(17.5rem,calc(100vw-2rem))] rounded-[1.5rem] p-2 shadow-2xl",
            )}
          >
            <ThreadListItemMorePrimitive.Item
              className={threadMenuItemClass}
              onSelect={() =>
                aui.threadListItem.updateCustom({
                  ...custom,
                  pinned: !isPinned,
                })
              }
            >
              {isPinned ? (
                <PinOffIcon className="size-4" />
              ) : (
                <PinIcon className="size-4" />
              )}
              {isPinned ? "Открепить" : "Закрепить"}
            </ThreadListItemMorePrimitive.Item>
            <ThreadListItemMorePrimitive.Item
              className={threadMenuItemClass}
              onSelect={() => {
                if (status === "archived") {
                  aui.threadListItem.unarchive();
                } else {
                  aui.threadListItem.archive();
                }
              }}
            >
              {status === "archived" ? (
                <ArchiveRestoreIcon className="size-4" />
              ) : (
                <ArchiveIcon className="size-4" />
              )}
              {status === "archived" ? "Вернуть из архива" : "Архивировать"}
            </ThreadListItemMorePrimitive.Item>
            <ThreadListItemMorePrimitive.Separator className="my-1 h-px bg-border" />
            <ThreadListItemMorePrimitive.Item
              className={cn(
                threadMenuItemClass,
                "text-destructive data-[highlighted]:bg-destructive/10",
              )}
              onSelect={() => {
                const confirmed = globalThis.confirm(
                  `Удалить диалог «${title}» из списка? Проект и документы сохранятся.`,
                );
                if (confirmed) aui.threadListItem.delete();
              }}
            >
              <Trash2Icon className="size-4" />
              Удалить диалог
            </ThreadListItemMorePrimitive.Item>
          </ThreadListItemMorePrimitive.Content>
        </ThreadListItemMorePrimitive.Root>
      ) : null}
    </ThreadListItemPrimitive.Root>
  );
};
