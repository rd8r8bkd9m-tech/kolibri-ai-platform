import { Copy, Download, MoreHorizontal, PencilLine } from "lucide-react";
import { cn, formatTime } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Sheet, SheetContent } from "@/components/ui/sheet";

interface MessageActionsProps {
  role: "user" | "assistant";
  canEdit: boolean;
  editing: boolean;
  copied: boolean;
  createdAt: string;
  editedAt?: string;
  sheetOpen: boolean;
  onSheetOpenChange: (open: boolean) => void;
  onEdit: () => void;
  onCopy: () => void;
  onDownload: () => void;
}

export function MessageActions({
  role,
  canEdit,
  editing,
  copied,
  createdAt,
  editedAt,
  sheetOpen,
  onSheetOpenChange,
  onEdit,
  onCopy,
  onDownload,
}: MessageActionsProps) {
  const handleEdit = () => {
    onSheetOpenChange(false);
    onEdit();
  };

  return (
    <>
      <div className={cn("mt-2 flex items-center gap-2 text-[11px]", role === "user" ? "text-zinc-500 dark:text-zinc-300" : "text-muted")}>
        <span>{formatTime(createdAt)}</span>
        {editedAt ? <span className="opacity-75">изменено</span> : null}
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
                  role === "user"
                    ? "text-zinc-500 hover:bg-zinc-300/60 hover:text-zinc-900 dark:text-zinc-300 dark:hover:bg-zinc-600"
                    : "text-muted hover:text-foreground",
                )}
              >
                <MoreHorizontal className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              {canEdit ? (
                <DropdownMenuItem onClick={onEdit}>
                  <PencilLine className="mr-2 h-4 w-4" />
                  Изменить и переспросить
                </DropdownMenuItem>
              ) : null}
              <DropdownMenuItem onClick={onCopy}>
                <Copy className="mr-2 h-4 w-4" />
                Копировать текст
              </DropdownMenuItem>
              {role === "assistant" ? (
                <DropdownMenuItem onClick={onDownload}>
                  <Download className="mr-2 h-4 w-4" />
                  Скачать Markdown
                </DropdownMenuItem>
              ) : null}
            </DropdownMenuContent>
          </DropdownMenu>
        ) : null}
      </div>

      <Sheet open={sheetOpen} onOpenChange={onSheetOpenChange}>
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
                  onClick={handleEdit}
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
                onClick={onCopy}
                className="flex items-center gap-3 rounded-[1.2rem] border border-border/10 bg-card/70 px-4 py-4 text-left"
              >
                <Copy className="h-5 w-5 text-emerald-400" />
                <span>
                  <span className="block text-sm font-semibold">Копировать текст</span>
                  <span className="block text-xs text-muted">Скопировать сообщение в буфер обмена</span>
                </span>
              </button>
              {role === "assistant" ? (
                <button
                  type="button"
                  onClick={onDownload}
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
    </>
  );
}
