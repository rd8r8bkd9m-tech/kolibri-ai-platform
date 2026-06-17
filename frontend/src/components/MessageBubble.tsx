import { memo, useEffect, useRef, useState } from "react";
import TextareaAutosize from "react-textarea-autosize";
import { cva } from "class-variance-authority";
import { BrainCircuit, Check, Copy, Download, FileText, Maximize2, Minimize2, MoreHorizontal, PencilLine, RotateCcw, SendHorizontal } from "lucide-react";
import { KolibriAvatar } from "@/components/kolibri/KolibriAvatar";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { sanitizeAssistantText } from "@/lib/answerSanitizer";
import { cn, formatTime } from "@/lib/utils";
import { renderMarkdown } from "@/lib/markdown";
import { useStreaming } from "@/hooks/useStreaming";
import { Sheet, SheetContent } from "@/components/ui/sheet";
import type { ChatMessage } from "@/types";

const bubbleVariants = cva("text-[15px] leading-[1.65]", {
  variants: {
    role: {
      user:
        "ml-auto max-w-[82%] rounded-[1.25rem] bg-zinc-200 px-4 py-3 text-zinc-950 shadow-none dark:bg-zinc-700 dark:text-zinc-50 lg:max-w-[72%]",
      assistant:
        "mr-auto flex w-full max-w-full gap-3 bg-transparent px-0 py-1 text-foreground shadow-none",
    }
  },
});

function renderCodeBlocks(content: string) {
  const blocks = content.split(/```/g);
  if (blocks.length < 2) {
    return <div className="markdown" dangerouslySetInnerHTML={{ __html: renderMarkdown(content) }} />;
  }

  return (
    <div className="space-y-3">
      {blocks.map((part, index) => {
        const isCode = index % 2 === 1;
        if (!isCode) {
          return <div key={index} className="markdown" dangerouslySetInnerHTML={{ __html: renderMarkdown(part) }} />;
        }
        const [lang, ...rest] = part.split("\n");
        return (
          <pre key={index} className="overflow-x-auto rounded-xl border border-border/10 bg-card/95 p-3">
            <code className="font-mono text-sm text-foreground">{rest.join("\n")}</code>
          </pre>
        );
      })}
    </div>
  );
}

function isDocumentLike(content: string) {
  const text = content.trim();
  if (text.length < 260) return false;

  const headingCount = (text.match(/^#{1,3}\s+\S/gm) ?? []).length;
  const inlineHeadings = (text.match(/(?:^|\s)#{2,3}\s+\S/g) ?? []).length;
  const numberedItems = (text.match(/^\s*\d+\.\s+\S/gm) ?? []).length;
  const bulletItems = (text.match(/^\s*[-*]\s+\S/gm) ?? []).length;
  const inlineChecklistItems = (text.match(/[-*]\s+\[[ xX]\]\s+\S/g) ?? []).length;
  const tableRows = (text.match(/^\|.+\|$/gm) ?? []).length;
  const documentWords = /\b(отч[её]т|документ|план|техническ(?:ий|ого)|регламент|инструкция|резюме|контроль качества|основная часть)\b/i.test(text);

  return (
    headingCount >= 2 ||
    inlineHeadings >= 2 ||
    tableRows >= 2 ||
    numberedItems >= 4 ||
    inlineChecklistItems >= 2 ||
    (documentWords && (headingCount + inlineHeadings >= 1 || bulletItems >= 3 || text.length > 900))
  );
}

function extractDocumentTitle(content: string) {
  const normalized = normalizeDocumentMarkdown(content);
  const firstHeading = normalized.match(/^#\s+(.+)$/m);
  if (firstHeading?.[1]) return firstHeading[1].trim();

  const firstLine = normalized
    .split("\n")
    .map((line) => line.trim())
    .find((line) => line.length > 0);

  if (!firstLine) return "Документ Kolibri";
  return firstLine.replace(/^#+\s*/, "").replace(/\s+#{2,3}\s+.*$/, "").slice(0, 90);
}

function normalizeDocumentMarkdown(content: string) {
  return content
    .replace(/\s+(#{2,3}\s+\S)/g, "\n\n$1")
    .replace(
      /^(#{2,3}\s+(?:Резюме|Архитектура процесса|Контроль качества и проверки|Проверки|План|Итог|Вывод|Основная часть|Рекомендации))\s+/gim,
      "$1\n\n",
    )
    .replace(/\s+(\d+\.\s+\*\*[^*]+:\*\*)/g, "\n\n$1")
    .replace(/\s+(\d+\.\s+\S)/g, "\n\n$1")
    .replace(/\s+([-*]\s+\[[ xX]\]\s+\S)/g, "\n$1")
    .replace(/\s+([-*]\s+\S)/g, "\n$1")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function countDocumentSections(content: string) {
  const headings = (content.match(/^#{1,3}\s+\S/gm) ?? []).length;
  const listItems = (content.match(/^\s*(?:[-*]|\d+\.)\s+\S/gm) ?? []).length;
  const tableRows = (content.match(/^\|.+\|$/gm) ?? []).length;
  return { headings, listItems, tableRows };
}

function DocumentView({ content }: { content: string }) {
  const normalizedContent = normalizeDocumentMarkdown(content);
  const [expanded, setExpanded] = useState(false);
  const stats = countDocumentSections(normalizedContent);

  return (
    <section className={cn("kolibri-document", expanded && "kolibri-document--expanded")} aria-label="Документ в чате">
      <div className="kolibri-document__bar">
        <div className="kolibri-document__badge">
          <FileText className="h-4 w-4" />
          Документ
        </div>
        <div className="kolibri-document__title">{extractDocumentTitle(normalizedContent)}</div>
        <button
          type="button"
          className="kolibri-document__toggle"
          onClick={() => setExpanded((value) => !value)}
          aria-expanded={expanded}
        >
          {expanded ? <Minimize2 className="h-3.5 w-3.5" /> : <Maximize2 className="h-3.5 w-3.5" />}
          {expanded ? "Свернуть" : "Открыть"}
        </button>
      </div>
      <div className="kolibri-document__meta" aria-label="Структура документа">
        <span>{stats.headings || 1} разделов</span>
        <span>{stats.listItems} пунктов</span>
        {stats.tableRows ? <span>{stats.tableRows} строк таблиц</span> : null}
      </div>
      <div className="kolibri-document__page">
        <div className="markdown document-markdown" dangerouslySetInnerHTML={{ __html: renderMarkdown(normalizedContent) }} />
      </div>
      {!expanded ? (
        <div className="kolibri-document__fade">
          <button type="button" onClick={() => setExpanded(true)}>
            Развернуть документ
          </button>
        </div>
      ) : null}
    </section>
  );
}

function MessageContent({ content, documentMode }: { content: string; documentMode: boolean }) {
  if (documentMode) {
    return <DocumentView content={content} />;
  }
  return renderCodeBlocks(content);
}

export const MessageBubble = memo(function MessageBubble({ message }: { message: ChatMessage }) {
  const { resendEditedMessage } = useStreaming();
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const [draft, setDraft] = useState(message.content);
  const holdTimerRef = useRef<number | null>(null);
  const canEdit = message.role === "user" && !message.streaming && !message.imageUrl;
  const hasImage = Boolean(message.imageUrl);
  const normalizedContent = message.role === "assistant" ? sanitizeAssistantText(message.content) : message.content;
  const hasContent = normalizedContent.trim().length > 0;
  const displayContent = hasContent ? normalizedContent : (message.streaming ? "Думаю..." : "");
  const reasoning = message.role === "assistant" ? message.reasoning ?? [] : [];
  const documentMode = message.role === "assistant" && !message.streaming && isDocumentLike(displayContent);

  useEffect(() => {
    if (!editing) setDraft(message.content);
  }, [editing, message.content]);

  useEffect(() => {
    if (!copied) return undefined;
    const timer = window.setTimeout(() => setCopied(false), 1600);
    return () => window.clearTimeout(timer);
  }, [copied]);

  const submitEdit = async () => {
    const next = draft.trim();
    if (!next || next === message.content.trim()) {
      setEditing(false);
      setDraft(message.content);
      return;
    }
    setSaving(true);
    try {
      await resendEditedMessage(message.id, next);
      setEditing(false);
    } finally {
      setSaving(false);
    }
  };

  const copyMessage = async () => {
    try {
      await navigator.clipboard.writeText(normalizedContent);
      setCopied(true);
    } catch {
      // noop
    }
    setSheetOpen(false);
  };

  const downloadMarkdown = () => {
    const blob = new Blob([normalizedContent], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    try {
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `kolibri-answer-${new Date(message.createdAt).toISOString().slice(0, 19).replace(/[:T]/g, "-")}.md`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
    } finally {
      URL.revokeObjectURL(url);
    }
    setSheetOpen(false);
  };

  const clearHold = () => {
    if (holdTimerRef.current !== null) {
      window.clearTimeout(holdTimerRef.current);
      holdTimerRef.current = null;
    }
  };

  return (
    <article
      className={cn("group mb-5 w-full", message.role === "user" ? "flex justify-end" : "flex justify-start")}
      onContextMenu={(event) => event.preventDefault()}
      onPointerDown={clearHold}
      onPointerUp={clearHold}
      onPointerCancel={clearHold}
      onPointerLeave={clearHold}
    >
      <div className={bubbleVariants({ role: message.role })}>
        {message.role === "assistant" ? (
          <KolibriAvatar state={message.streaming ? "writing" : "calm"} size="sm" className="mt-1 hidden shrink-0 md:block" />
        ) : null}
        <div className="min-w-0 flex-1">
          {editing ? (
            <div className="space-y-2">
              <TextareaAutosize
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                minRows={2}
                maxRows={8}
                className="w-full resize-none rounded-2xl border border-foreground/10 bg-background px-3 py-2 text-[14px] leading-[1.5] text-foreground outline-none"
              />
              <div className="flex items-center justify-end gap-2 text-[11px]">
                <button
                  type="button"
                  onClick={() => {
                    setEditing(false);
                    setDraft(message.content);
                  }}
                  className="inline-flex items-center gap-1 rounded-full border border-foreground/10 px-3 py-1.5 text-muted"
                >
                  <RotateCcw className="h-3.5 w-3.5" />
                  Отмена
                </button>
                <button
                  type="button"
                  disabled={saving}
                  onClick={() => void submitEdit()}
                  className="inline-flex items-center gap-1 rounded-full bg-foreground px-3 py-1.5 font-semibold text-background disabled:opacity-60"
                >
                  {saving ? <SendHorizontal className="h-3.5 w-3.5 animate-pulse" /> : <Check className="h-3.5 w-3.5" />}
                  Сохранить и отправить
                </button>
              </div>
            </div>
          ) : displayContent ? <MessageContent content={displayContent} documentMode={documentMode} /> : null}
          {message.streaming ? <span className="ml-1 inline-block h-4 w-0.5 animate-pulse bg-foreground/70 align-middle" /> : null}
          {reasoning.length > 0 && !message.streaming ? (
            <div className="mt-3 rounded-2xl border border-emerald-500/15 bg-emerald-500/[0.04] px-3 py-2">
              <div className="flex items-center gap-2 text-[12px] font-semibold text-emerald-700 dark:text-emerald-300">
                <BrainCircuit className="h-3.5 w-3.5" />
                Видимое мышление Kolibri
              </div>
              <div className="mt-1.5 grid gap-1 text-[12px] leading-5 text-muted">
                {reasoning.slice(-4).map((step, index) => (
                  <div key={`${step}-${index}`}>• {step}</div>
                ))}
              </div>
            </div>
          ) : null}
          {hasImage ? (
            <a href={message.imageUrl} target="_blank" rel="noreferrer" className="group mt-3 block overflow-hidden rounded-xl border border-border/15 bg-card/60">
              <img src={message.imageUrl} alt="Сгенерированное изображение" className="max-h-[38rem] w-full object-cover transition duration-300 group-hover:scale-[1.01]" loading="lazy" />
            </a>
          ) : null}
          <div className={cn("mt-2 flex items-center gap-2 text-[11px]", message.role === "user" ? "text-zinc-500 dark:text-zinc-300" : "text-muted")}>
            <span>{formatTime(message.createdAt)}</span>
            {message.editedAt ? <span className="opacity-75">изменено</span> : null}
            {copied ? <span className="opacity-75">скопировано</span> : null}
            {!editing ? (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    aria-label="Действия с сообщением"
                    className={cn(
                      "ml-auto hidden h-7 w-7 rounded-full",
                      message.role === "user"
                        ? "text-zinc-500 hover:bg-zinc-300/60 hover:text-zinc-900 dark:text-zinc-300 dark:hover:bg-zinc-600"
                        : "text-muted hover:text-foreground",
                    )}
                  >
                    <MoreHorizontal className="h-4 w-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  {canEdit ? (
                    <DropdownMenuItem
                      onClick={() => {
                        setEditing(true);
                      }}
                    >
                      <PencilLine className="mr-2 h-4 w-4" />
                      Изменить и переспросить
                    </DropdownMenuItem>
                  ) : null}
                  <DropdownMenuItem onClick={() => void copyMessage()}>
                    <Copy className="mr-2 h-4 w-4" />
                    Копировать текст
                  </DropdownMenuItem>
                  {message.role === "assistant" ? (
                    <DropdownMenuItem onClick={downloadMarkdown}>
                      <Download className="mr-2 h-4 w-4" />
                      Скачать Markdown
                    </DropdownMenuItem>
                  ) : null}
                </DropdownMenuContent>
              </DropdownMenu>
            ) : null}
          </div>
        </div>
      </div>

      <Sheet open={sheetOpen} onOpenChange={setSheetOpen}>
        <SheetContent
          title="Действия"
          description="Быстрые действия с сообщением"
          className="inset-x-0 left-0 right-0 top-auto z-50 h-auto max-w-none rounded-t-[2rem] border-r-0 border-t border-border/10 bg-background/95 px-4 pb-[calc(env(safe-area-inset-bottom)+1rem)] pt-4"
        >
          <div className="mx-auto w-full max-w-xl">
            <div className="mx-auto mb-3 h-1.5 w-14 rounded-full bg-border/30" />
            <p className="text-base font-semibold">Действия с сообщением</p>
            <div className="mt-4 grid gap-2">
              {canEdit ? (
                <button
                  type="button"
                  onClick={() => {
                    setSheetOpen(false);
                    setEditing(true);
                  }}
                  className="flex items-center gap-3 rounded-[1.2rem] border border-border/10 bg-card/70 px-4 py-4 text-left"
                >
                  <PencilLine className="h-5 w-5 text-cyan-400" />
                  <span>
                    <span className="block text-sm font-semibold">Изменить и переспросить</span>
                    <span className="block text-xs text-muted">Перепишет запрос и отправит новую ветку ответа</span>
                  </span>
                </button>
              ) : null}
              <button
                type="button"
                onClick={() => void copyMessage()}
                className="flex items-center gap-3 rounded-[1.2rem] border border-border/10 bg-card/70 px-4 py-4 text-left"
              >
                <Copy className="h-5 w-5 text-emerald-400" />
                <span>
                  <span className="block text-sm font-semibold">Копировать текст</span>
                  <span className="block text-xs text-muted">Скопировать сообщение в буфер обмена</span>
                </span>
              </button>
              {message.role === "assistant" ? (
                <button
                  type="button"
                  onClick={downloadMarkdown}
                  className="flex items-center gap-3 rounded-[1.2rem] border border-border/10 bg-card/70 px-4 py-4 text-left"
                >
                  <Download className="h-5 w-5 text-sky-500" />
                  <span>
                    <span className="block text-sm font-semibold">Скачать Markdown</span>
                    <span className="block text-xs text-muted">Сохранить длинный ответ как документ .md</span>
                  </span>
                </button>
              ) : null}
            </div>
          </div>
        </SheetContent>
      </Sheet>
    </article>
  );
});
