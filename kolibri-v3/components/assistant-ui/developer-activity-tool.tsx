"use client";

import { makeAssistantToolUI } from "@assistant-ui/react";
import {
  CheckCircle2Icon,
  ChevronRightIcon,
  FileCode2Icon,
  LoaderCircleIcon,
  TerminalSquareIcon,
} from "lucide-react";

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const decodeResult = (value: unknown): Record<string, unknown> | null => {
  if (isRecord(value)) return value;
  if (typeof value !== "string") return null;
  try {
    const decoded = JSON.parse(value) as unknown;
    return isRecord(decoded) ? decoded : null;
  } catch {
    return null;
  }
};

export const DeveloperCommandToolUI = makeAssistantToolUI({
  toolName: "developer_command",
  render: ({ args, result, status }) => {
    const completed = status.type !== "running";
    const decoded = decodeResult(result);
    const command =
      typeof args.command === "string" && args.command ? args.command : null;
    return (
      <details
        className="border-border/70 bg-muted/20 group/developer-tool rounded-lg border"
        aria-label="Команда агента-разработчика"
      >
        <summary className="hover:bg-muted/35 flex min-h-9 cursor-pointer list-none items-center gap-2 rounded-lg px-2.5 py-1.5 text-xs font-medium transition-colors [&::-webkit-details-marker]:hidden">
          {completed ? (
            <CheckCircle2Icon
              className="size-3.5 shrink-0 text-emerald-600"
              aria-hidden="true"
            />
          ) : (
            <LoaderCircleIcon
              className="size-3.5 shrink-0 animate-spin"
              aria-hidden="true"
            />
          )}
          <TerminalSquareIcon className="size-3.5 shrink-0" aria-hidden="true" />
          <span className="shrink-0">
            {completed ? "Команда выполнена" : "Выполняется команда"}
          </span>
          {command ? (
            <code className="text-muted-foreground ml-auto min-w-0 truncate text-[10px] font-normal">
              {command}
            </code>
          ) : null}
          <ChevronRightIcon
            className="size-3.5 shrink-0 transition-transform group-open/developer-tool:rotate-90"
            aria-hidden="true"
          />
        </summary>
        <div className="border-border/60 border-t px-2.5 py-2">
          {command ? (
            <pre className="bg-background/80 max-h-72 overflow-auto rounded-md px-2.5 py-2 text-[11px] whitespace-pre-wrap">
              {command}
            </pre>
          ) : null}
          <footer className="text-muted-foreground mt-1.5 flex flex-wrap gap-3 text-[11px]">
            {typeof args.cwd === "string" && args.cwd ? (
              <span>{args.cwd}</span>
            ) : null}
            {typeof decoded?.exitCode === "number" ? (
              <span>exit {decoded.exitCode}</span>
            ) : null}
            {typeof decoded?.durationMs === "number" ? (
              <span>{Math.round(decoded.durationMs)} мс</span>
            ) : null}
          </footer>
        </div>
      </details>
    );
  },
});

export const DeveloperFileChangeToolUI = makeAssistantToolUI({
  toolName: "developer_file_change",
  render: ({ args, result, status }) => {
    const decoded = decodeResult(result);
    const rawChanges = Array.isArray(decoded?.changes)
      ? decoded.changes
      : Array.isArray(args.files)
        ? args.files
        : [];
    const changes = rawChanges.filter(isRecord).slice(0, 40);
    const changesLabel =
      changes.length > 0 ? `${changes.length} файл.` : "Файлы";
    return (
      <details
        className="border-border/70 bg-muted/20 group/developer-tool rounded-lg border"
        aria-label="Изменения файлов агентом-разработчиком"
      >
        <summary className="hover:bg-muted/35 flex min-h-9 cursor-pointer list-none items-center gap-2 rounded-lg px-2.5 py-1.5 text-xs font-medium transition-colors [&::-webkit-details-marker]:hidden">
          {status.type === "running" ? (
            <LoaderCircleIcon
              className="size-3.5 shrink-0 animate-spin"
              aria-hidden="true"
            />
          ) : (
            <CheckCircle2Icon
              className="size-3.5 shrink-0 text-emerald-600"
              aria-hidden="true"
            />
          )}
          <FileCode2Icon className="size-3.5 shrink-0" aria-hidden="true" />
          <span className="shrink-0">
            {status.type === "running"
              ? "Изменяются файлы"
              : "Файлы изменены"}
          </span>
          <span className="text-muted-foreground ml-auto truncate text-[10px] font-normal">
            {changesLabel}
          </span>
          <ChevronRightIcon
            className="size-3.5 shrink-0 transition-transform group-open/developer-tool:rotate-90"
            aria-hidden="true"
          />
        </summary>
        <div className="border-border/60 space-y-2 border-t px-2.5 py-2">
          {changes.map((change, index) => {
            const path =
              typeof change.path === "string"
                ? change.path
                : `file-${index + 1}`;
            const diff =
              typeof change.diff === "string" ? change.diff : "";
            return (
              <details
                key={`${path}:${index}`}
                className="border-border/60 bg-background/70 rounded-lg border"
              >
                <summary className="cursor-pointer px-2.5 py-2 text-[11px] font-medium">
                  {path}
                </summary>
                {diff ? (
                  <pre className="border-border/60 max-h-72 overflow-auto border-t px-2.5 py-2 text-[10px] whitespace-pre">
                    {diff}
                  </pre>
                ) : null}
              </details>
            );
          })}
        </div>
      </details>
    );
  },
});

export function DeveloperActivityToolUIs() {
  return (
    <>
      <DeveloperCommandToolUI />
      <DeveloperFileChangeToolUI />
    </>
  );
}
