"use client";

import { Thread } from "@/components/assistant-ui/thread";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { AssistantModalPrimitive } from "@assistant-ui/react";
import {
  MessageCircleIcon,
  PanelBottomIcon,
  PanelRightIcon,
  PinIcon,
  PinOffIcon,
  SparklesIcon,
  XIcon,
} from "lucide-react";

export type AssistantChatDock = "bottom" | "right";

export type AssistantChatWidgetProps = {
  dock?: AssistantChatDock;
  pinned: boolean;
  open: boolean;
  onDockChange?: (dock: AssistantChatDock) => void;
  onOpenAccount?: () => void;
  onOpenDesktop?: () => void;
  onPinnedChange: (pinned: boolean) => void;
  onOpenChange: (open: boolean) => void;
  className?: string;
};

/**
 * One assistant-ui thread that can move between a floating modal and an
 * inline, pinned panel. The two modes are mutually exclusive so the runtime
 * never mounts duplicate Thread primitives.
 */
export function AssistantChatWidget({
  dock = "right",
  pinned,
  open,
  onDockChange,
  onOpenAccount,
  onOpenDesktop,
  onPinnedChange,
  onOpenChange,
  className,
}: AssistantChatWidgetProps) {
  const pin = () => {
    onOpenChange(true);
    onPinnedChange(true);
  };

  const unpin = () => {
    onOpenChange(true);
    onPinnedChange(false);
  };

  const closePinned = () => {
    onPinnedChange(false);
    onOpenChange(false);
  };

  if (pinned) {
    return (
      <section
        data-slot="assistant-chat-widget-pinned"
        aria-label="Закреплённый чат с Kolibri"
        className={cn(
          "bg-background flex h-full min-h-0 min-w-0 flex-col overflow-hidden border-l",
          className,
        )}
      >
        <AssistantWidgetHeader
          dock={dock}
          pinned
          onDockChange={onDockChange}
          onPinnedChange={unpin}
          onClose={closePinned}
        />
        <AssistantWidgetThread
          onOpenAccount={onOpenAccount}
          onOpenDesktop={onOpenDesktop}
        />
      </section>
    );
  }

  return (
    <TooltipProvider delayDuration={300}>
      <AssistantModalPrimitive.Root
        open={open}
        onOpenChange={onOpenChange}
        unstable_openOnRunStart
      >
        <Tooltip>
          <TooltipTrigger asChild>
            <AssistantModalPrimitive.Trigger asChild>
              <Button
                type="button"
                size="lg"
                aria-label="Открыть чат с Kolibri"
                data-slot="assistant-chat-trigger"
                className="absolute right-4 bottom-[calc(5.5rem+env(safe-area-inset-bottom))] z-[60] h-11 rounded-full bg-neutral-950 px-4 text-white shadow-[0_12px_30px_-16px_rgba(0,0,0,0.7)] hover:bg-neutral-800 focus-visible:ring-neutral-400 min-[960px]:right-5 min-[960px]:bottom-[calc(1.25rem+env(safe-area-inset-bottom))]"
              >
                <MessageCircleIcon className="size-4" aria-hidden="true" />
                <span>Kolibri</span>
              </Button>
            </AssistantModalPrimitive.Trigger>
          </TooltipTrigger>
          <TooltipContent side="left" sideOffset={8}>
            Открыть чат с Kolibri
          </TooltipContent>
        </Tooltip>

        <AssistantModalPrimitive.Content
          side="top"
          align="end"
          sideOffset={12}
          collisionPadding={8}
          dissmissOnInteractOutside={false}
          aria-label="Чат с Kolibri"
          className={cn(
            "bg-background z-[70] flex h-[min(42rem,calc(100dvh-5.75rem))] w-[calc(100vw-1rem)] min-w-0 flex-col overflow-hidden rounded-2xl border shadow-[0_24px_70px_-34px_rgba(0,0,0,0.55),0_8px_24px_-16px_rgba(0,0,0,0.24)] outline-none",
            "sm:h-[min(42rem,calc(100dvh-6.5rem))] sm:w-[25rem]",
            className,
          )}
        >
          <AssistantWidgetHeader
            dock={dock}
            pinned={false}
            onDockChange={onDockChange}
            onPinnedChange={pin}
            onClose={() => onOpenChange(false)}
          />
          <AssistantWidgetThread
            onOpenAccount={onOpenAccount}
            onOpenDesktop={onOpenDesktop}
          />
        </AssistantModalPrimitive.Content>
      </AssistantModalPrimitive.Root>
    </TooltipProvider>
  );
}

function AssistantWidgetHeader({
  dock,
  pinned,
  onDockChange,
  onPinnedChange,
  onClose,
}: {
  dock: AssistantChatDock;
  pinned: boolean;
  onDockChange?: (dock: AssistantChatDock) => void;
  onPinnedChange: () => void;
  onClose: () => void;
}) {
  const pinLabel = pinned ? "Открепить чат" : "Закрепить чат";

  return (
    <header className="flex h-13 shrink-0 items-center gap-3 border-b px-3">
      <div
        className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-neutral-950 text-white"
        aria-hidden="true"
      >
        <SparklesIcon className="size-3.5" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-semibold">Kolibri</p>
        <p className="text-muted-foreground truncate text-[11px]">
          Контекст текущей рабочей области
        </p>
      </div>

      {pinned && onDockChange ? (
        <>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                onClick={() => onDockChange("right")}
                aria-label="Закрепить чат справа"
                aria-pressed={dock === "right"}
                className={dock === "right" ? "bg-muted" : undefined}
              >
                <PanelRightIcon aria-hidden="true" />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="bottom" sideOffset={6}>
              Закрепить справа
            </TooltipContent>
          </Tooltip>

          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                onClick={() => onDockChange("bottom")}
                aria-label="Закрепить чат снизу"
                aria-pressed={dock === "bottom"}
                className={dock === "bottom" ? "bg-muted" : undefined}
              >
                <PanelBottomIcon aria-hidden="true" />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="bottom" sideOffset={6}>
              Закрепить снизу
            </TooltipContent>
          </Tooltip>
        </>
      ) : null}

      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            onClick={onPinnedChange}
            aria-label={pinLabel}
            aria-pressed={pinned}
          >
            {pinned ? (
              <PinOffIcon aria-hidden="true" />
            ) : (
              <PinIcon aria-hidden="true" />
            )}
          </Button>
        </TooltipTrigger>
        <TooltipContent side="bottom" sideOffset={6}>
          {pinLabel}
        </TooltipContent>
      </Tooltip>

      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            onClick={onClose}
            aria-label="Закрыть чат"
          >
            <XIcon aria-hidden="true" />
          </Button>
        </TooltipTrigger>
        <TooltipContent side="bottom" sideOffset={6}>
          Закрыть чат
        </TooltipContent>
      </Tooltip>
    </header>
  );
}

function AssistantWidgetThread({
  onOpenAccount,
  onOpenDesktop,
}: {
  onOpenAccount?: () => void;
  onOpenDesktop?: () => void;
}) {
  return (
    <div
      data-slot="assistant-chat-widget-thread"
      className="min-h-0 min-w-0 flex-1 [&_.aui-thread-welcome-message-inner]:text-xl [&_.aui-thread-welcome-suggestions]:hidden"
    >
      <Thread
        onOpenAccount={onOpenAccount}
        onOpenDesktop={onOpenDesktop}
      />
    </div>
  );
}
