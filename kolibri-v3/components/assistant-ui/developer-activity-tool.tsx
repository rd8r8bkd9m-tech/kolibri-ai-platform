"use client";

import { makeAssistantToolUI } from "@assistant-ui/react";
import {
  CheckCircle2Icon,
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
    return (
      <section
        className="border-border/70 bg-muted/20 my-2 rounded-xl border px-3 py-2.5"
        aria-label="Команда агента-разработчика"
      >
        <header className="flex items-center gap-2 text-xs font-medium">
          {completed ? (
            <CheckCircle2Icon
              className="size-4 text-emerald-600"
              aria-hidden="true"
            />
          ) : (
            <LoaderCircleIcon
              className="size-4 animate-spin"
              aria-hidden="true"
            />
          )}
          <TerminalSquareIcon className="size-4" aria-hidden="true" />
          {completed ? "Команда выполнена" : "Выполняется команда"}
        </header>
        {typeof args.command === "string" && args.command ? (
          <pre className="bg-background/80 mt-2 overflow-x-auto rounded-lg px-2.5 py-2 text-[11px] whitespace-pre-wrap">
            {args.command}
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
        {typeof decoded?.output === "string" && decoded.output ? (
          <details className="border-border/60 bg-background/70 mt-2 rounded-lg border">
            <summary className="cursor-pointer px-2.5 py-2 text-[11px] font-medium">
              Вывод команды
            </summary>
            <pre className="border-border/60 max-h-72 overflow-auto border-t px-2.5 py-2 text-[10px] whitespace-pre-wrap">
              {decoded.output}
            </pre>
          </details>
        ) : null}
      </section>
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
    return (
      <section
        className="border-border/70 bg-muted/20 my-2 rounded-xl border px-3 py-2.5"
        aria-label="Изменения файлов агентом-разработчиком"
      >
        <header className="flex items-center gap-2 text-xs font-medium">
          {status.type === "running" ? (
            <LoaderCircleIcon
              className="size-4 animate-spin"
              aria-hidden="true"
            />
          ) : (
            <CheckCircle2Icon
              className="size-4 text-emerald-600"
              aria-hidden="true"
            />
          )}
          <FileCode2Icon className="size-4" aria-hidden="true" />
          {status.type === "running"
            ? "Изменяются файлы"
            : "Файлы изменены"}
        </header>
        <div className="mt-2 space-y-2">
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
      </section>
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
