"use client";

import { Maximize2 } from "lucide-react";

import type { CanvasTab } from "./canvas-session";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export type WorkspaceTaskShelfProps = {
  className?: string;
  onRestoreTab: (tabId: string) => void;
  tabs: readonly CanvasTab[];
};

export function WorkspaceTaskShelf({
  className,
  onRestoreTab,
  tabs,
}: WorkspaceTaskShelfProps) {
  const minimizedTabs = tabs.filter((tab) => tab.minimized);

  if (minimizedTabs.length === 0) return null;

  return (
    <section
      data-slot="workspace-task-shelf"
      aria-label="Свёрнутые вкладки рабочей области"
      className={cn(
        "border-border bg-background shrink-0 border-t px-2 pt-1.5 pb-[max(0.375rem,env(safe-area-inset-bottom))]",
        className,
      )}
    >
      <p
        className="sr-only"
        role="status"
        aria-atomic="true"
        aria-live="polite"
      >
        Свёрнуто вкладок: {minimizedTabs.length}
      </p>

      <ul className="flex min-w-0 gap-1.5 overflow-x-auto overscroll-x-contain">
        {minimizedTabs.map((tab) => (
          <li key={tab.id} className="shrink-0">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="min-h-11 max-w-64 justify-start rounded-lg px-3 text-xs shadow-none"
              data-canvas-restore-tab={tab.id}
              aria-label={`Восстановить вкладку «${tab.title}»`}
              onClick={() => onRestoreTab(tab.id)}
            >
              <Maximize2
                className="text-muted-foreground size-3.5 shrink-0"
                aria-hidden="true"
              />
              <span className="truncate">{tab.title}</span>
            </Button>
          </li>
        ))}
      </ul>
    </section>
  );
}
