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
      className="relative flex shrink-0 items-center bg-background"
    >
      <div className="flex w-full items-center justify-between px-3">
        {onBack ? (
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={onBack}
            aria-label="На основной экран"
            data-slot="mobile-editor-back"
            className="size-10 shrink-0 rounded-lg"
          >
            <ChevronLeft
              aria-hidden="true"
              className="size-5 stroke-[1.75]"
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
            className="size-10 shrink-0 rounded-lg"
          >
            <span
              data-slot="mobile-hamburger-icon"
              aria-hidden="true"
              className="flex w-5 flex-col gap-[5px]"
            >
              <span className="h-[1.5px] w-full rounded-full bg-current" />
              <span className="h-[1.5px] w-full rounded-full bg-current" />
            </span>
          </Button>
        )}

        {isChat && !onBack && onOpenDestination ? (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                type="button"
                className="focus-visible:ring-ring flex h-8 items-center gap-1 rounded-lg px-2 text-sm font-medium tracking-tight outline-none focus-visible:ring-2"
                aria-label="Chat. Выбрать раздел"
              >
                <span>Kolibri</span>
                <ChevronDown
                  aria-hidden="true"
                  className="text-muted-foreground size-3.5 stroke-[2]"
                />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent
              align="center"
              sideOffset={8}
              className="z-[80] w-[min(15rem,calc(100vw-2rem))] rounded-xl p-1 shadow-lg"
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
                  className="min-h-9 rounded-lg px-3 text-sm"
                >
                  <span className="min-w-0 flex-1 truncate">
                    {destination.label}
                  </span>
                  {destination.id === "chat" ? (
                    <Check aria-hidden="true" className="size-4" />
                  ) : null}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        ) : (
          <h1 className="pointer-events-none absolute left-1/2 max-w-[55vw] -translate-x-1/2 truncate text-sm font-medium tracking-tight">
            {title}
          </h1>
        )}

        {onBack ? (
          <span aria-hidden="true" className="size-10 shrink-0" />
        ) : isChat || isProjects ? (
          <ThreadListPrimitive.New asChild>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label={isProjects ? "Новая задача" : "Новый чат"}
              onClick={isProjects ? onOpenChat : undefined}
              className="size-10 shrink-0 rounded-lg"
            >
              {isProjects ? (
                <Plus aria-hidden="true" className="size-5 stroke-[1.75]" />
              ) : (
                <MessageCircle
                  aria-hidden="true"
                  className="size-5 stroke-[1.75]"
                />
              )}
            </Button>
          </ThreadListPrimitive.New>
        ) : (
          <span aria-hidden="true" className="size-10 shrink-0" />
        )}
      </div>
    </header>
  );
}
