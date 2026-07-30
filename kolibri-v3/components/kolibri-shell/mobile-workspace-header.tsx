"use client";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ThreadListPrimitive } from "@assistant-ui/react";
import {
  Check,
  ChevronDown,
  ChevronLeft,
  MessageCircle,
  Plus,
} from "lucide-react";

type MobileWorkspaceHeaderProps = {
  navigationOpen?: boolean;
  onBack?: () => void;
  onOpenChat?: () => void;
  onOpenDestination?: (
    destination:
      | "chat"
      | "desktop"
      | "projects"
      | "documents"
      | "references",
  ) => void;
  onToggleNavigation: () => void;
  title?: string;
};

export function MobileWorkspaceHeader({
  navigationOpen = false,
  onBack,
  onOpenChat,
  onOpenDestination,
  onToggleNavigation,
  title = "Chat",
}: MobileWorkspaceHeaderProps) {
  const isChat = title === "Chat";
  const isProjects = title === "Проекты";

  return (
    <header
      data-slot="kolibri-mobile-header"
      className="relative h-[6.5rem] shrink-0 bg-background"
    >
      <div className="absolute inset-x-0 top-[calc(1.35rem+env(safe-area-inset-top))] flex items-center justify-between px-[15px]">
        {onBack ? (
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={onBack}
            aria-label="На основной экран"
            data-slot="mobile-editor-back"
            className="size-12 rounded-full border border-foreground/45 bg-background p-0 shadow-none hover:bg-muted"
          >
            <ChevronLeft
              aria-hidden="true"
              className="size-8 -translate-x-px stroke-[2.2]"
            />
          </Button>
        ) : (
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={onToggleNavigation}
            aria-label="Открыть меню"
            aria-controls="workspace-project-navigation"
            aria-expanded={navigationOpen}
            className="size-12 rounded-full border border-foreground/45 bg-background p-0 shadow-none hover:bg-muted"
          >
            <span
              data-slot="mobile-hamburger-icon"
              aria-hidden="true"
              className="flex w-6 flex-col gap-[7px]"
            >
              <span className="h-[2.5px] w-full rounded-full bg-current" />
              <span className="h-[2.5px] w-full rounded-full bg-current" />
            </span>
          </Button>
        )}

        {isChat && !onBack && onOpenDestination ? (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                type="button"
                className="focus-visible:ring-ring absolute left-1/2 flex h-11 -translate-x-1/2 items-center gap-1 rounded-xl px-2 text-[21px] leading-none font-semibold tracking-[-0.035em] underline decoration-[1.5px] underline-offset-4 outline-none focus-visible:ring-2"
                aria-label="Chat. Выбрать раздел"
              >
                <span>Chat</span>
                <ChevronDown
                  aria-hidden="true"
                  className="text-muted-foreground size-5 stroke-[2]"
                />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent
              align="center"
              sideOffset={8}
              className="z-[80] w-[min(17rem,calc(100vw-2rem))] rounded-[1.75rem] border-foreground/35 p-2 shadow-xl"
            >
              {[
                { id: "chat", label: "Chat" },
                { id: "desktop", label: "Рабочий стол" },
                { id: "projects", label: "Проекты" },
                { id: "documents", label: "Документы" },
                { id: "references", label: "Справочники" },
              ].map((destination) => (
                <DropdownMenuItem
                  key={destination.id}
                  onSelect={() =>
                    onOpenDestination(
                      destination.id as
                        | "chat"
                        | "desktop"
                        | "projects"
                        | "documents"
                        | "references",
                    )
                  }
                  className="min-h-12 rounded-2xl px-4 text-[17px]"
                >
                  <span className="min-w-0 flex-1 truncate">
                    {destination.label}
                  </span>
                  {destination.id === "chat" ? (
                    <Check aria-hidden="true" className="size-5" />
                  ) : null}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        ) : (
          <h1 className="pointer-events-none absolute left-1/2 max-w-[58vw] -translate-x-1/2 truncate text-[21px] leading-none font-semibold tracking-[-0.035em]">
            {title}
          </h1>
        )}

        {onBack ? (
          <span aria-hidden="true" className="size-12 shrink-0" />
        ) : isChat || isProjects ? (
          <ThreadListPrimitive.New asChild>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label={isProjects ? "Новая задача" : "Новый чат"}
              onClick={isProjects ? onOpenChat : undefined}
              className="size-12 rounded-full border border-foreground/45 bg-background p-0 shadow-none hover:bg-muted"
            >
              {isProjects ? (
                <Plus aria-hidden="true" className="size-8 stroke-[1.7]" />
              ) : (
                <MessageCircle
                  aria-hidden="true"
                  className="size-7 stroke-[1.8]"
                />
              )}
            </Button>
          </ThreadListPrimitive.New>
        ) : (
          <span aria-hidden="true" className="size-12 shrink-0" />
        )}
      </div>
    </header>
  );
}
