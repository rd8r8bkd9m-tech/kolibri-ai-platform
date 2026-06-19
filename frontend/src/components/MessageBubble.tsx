import { memo, useEffect, useRef, useState } from "react";
import TextareaAutosize from "react-textarea-autosize";
import { cva } from "class-variance-authority";
import { BrainCircuit, Check, RotateCcw, SendHorizontal } from "lucide-react";
import { KolibriAvatar } from "@/components/kolibri/KolibriAvatar";
import { sanitizeAssistantText } from "@/lib/answerSanitizer";
import { cn } from "@/lib/utils";
import { renderMarkdown } from "@/lib/markdown";
import { useStreaming } from "@/hooks/useStreaming";
import type { ChatMessage } from "@/types";
import { isDocumentLike } from "@/components/message/documentUtils";
import { DocumentView } from "@/components/message/DocumentView";
import { MessageActions } from "@/components/message/MessageActions";

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
          <MessageActions
            role={message.role}
            canEdit={canEdit}
            editing={editing}
            copied={copied}
            createdAt={message.createdAt}
            editedAt={message.editedAt}
            sheetOpen={sheetOpen}
            onSheetOpenChange={setSheetOpen}
            onEdit={() => setEditing(true)}
            onCopy={() => void copyMessage()}
            onDownload={downloadMarkdown}
          />
        </div>
      </div>
    </article>
  );
});
