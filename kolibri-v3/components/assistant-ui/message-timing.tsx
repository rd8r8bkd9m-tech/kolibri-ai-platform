"use client";

import { useMessageTiming } from "@assistant-ui/react";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import type { FC } from "react";

const formatTimingMs = (milliseconds: number | undefined): string => {
  if (milliseconds === undefined) return "—";
  if (milliseconds < 1_000) return `${Math.round(milliseconds)} мс`;
  return `${(milliseconds / 1_000).toFixed(2)} с`;
};

/**
 * Official assistant-ui timing pattern, localized for Kolibri. It stays in
 * the message action bar so the primary reading surface remains quiet.
 */
export const MessageTiming: FC<{
  className?: string;
  side?: "top" | "right" | "bottom" | "left";
}> = ({ className, side = "right" }) => {
  const timing = useMessageTiming();
  if (timing?.totalStreamTime === undefined) return null;

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          data-slot="message-timing-trigger"
          aria-label="Статистика ответа"
          className={cn(
            "text-muted-foreground hover:bg-accent hover:text-accent-foreground flex items-center rounded-md p-1 font-mono text-xs tabular-nums transition-colors",
            className,
          )}
        >
          {formatTimingMs(timing.totalStreamTime)}
        </button>
      </TooltipTrigger>
      <TooltipContent
        side={side}
        sideOffset={8}
        data-slot="message-timing-popover"
        className="bg-popover text-popover-foreground rounded-lg border px-3 py-2 shadow-md [&_span>svg]:hidden!"
      >
        <div className="grid min-w-44 gap-1.5 text-xs">
          {timing.firstTokenTime !== undefined ? (
            <div className="flex items-center justify-between gap-4">
              <span className="text-muted-foreground">До первого фрагмента</span>
              <span className="font-mono tabular-nums">
                {formatTimingMs(timing.firstTokenTime)}
              </span>
            </div>
          ) : null}
          <div className="flex items-center justify-between gap-4">
            <span className="text-muted-foreground">Весь ответ</span>
            <span className="font-mono tabular-nums">
              {formatTimingMs(timing.totalStreamTime)}
            </span>
          </div>
          {timing.tokensPerSecond !== undefined ? (
            <div className="flex items-center justify-between gap-4">
              <span className="text-muted-foreground">Скорость, оценка</span>
              <span className="font-mono tabular-nums">
                {timing.tokensPerSecond.toFixed(1)} ток/с
              </span>
            </div>
          ) : null}
          <div className="flex items-center justify-between gap-4">
            <span className="text-muted-foreground">Фрагменты</span>
            <span className="font-mono tabular-nums">
              {timing.totalChunks}
            </span>
          </div>
          <p className="text-muted-foreground border-t pt-1.5 leading-relaxed">
            Клиентское измерение текущей сессии
          </p>
        </div>
      </TooltipContent>
    </Tooltip>
  );
};
