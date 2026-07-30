"use client";

import {
  ComposerAttachments,
  UserMessageAttachments,
} from "@/components/assistant-ui/attachment";
import { AgentProfileSelector } from "@/components/assistant-ui/agent-profile-selector";
import { ThreadFollowupSuggestions } from "@/components/assistant-ui/follow-up-suggestions";
import { KolibriGenerativeUI } from "@/components/assistant-ui/generative-ui-renderer";
import { MarkdownText } from "@/components/assistant-ui/markdown-text";
import { MessageTiming } from "@/components/assistant-ui/message-timing";
import {
  ReasoningContent,
  ReasoningRoot,
  ReasoningText,
  ReasoningTrigger,
} from "@/components/assistant-ui/reasoning";
import { ToolFallback } from "@/components/assistant-ui/tool-fallback";
import {
  ToolGroupContent,
  ToolGroupRoot,
  ToolGroupTrigger,
} from "@/components/assistant-ui/tool-group";
import { TooltipIconButton } from "@/components/assistant-ui/tooltip-icon-button";
import { Button } from "@/components/ui/button";
import {
  prepareEstimateShareFiles,
  sharePreparedEstimateFiles,
  shareResultMessage,
} from "@/lib/estimate-share";
import { parseNativeKolibriGenerativeUI } from "@/lib/generative-ui";
import { useIdentity } from "@/lib/identity/provider";
import { cn } from "@/lib/utils";
import {
  ActionBarPrimitive,
  AuiIf,
  type AssistantState,
  BranchPickerPrimitive,
  ComposerPrimitive,
  ErrorPrimitive,
  groupPartByType,
  MessagePrimitive,
  ThreadPrimitive,
  type ToolCallMessagePartComponent,
  useAuiEvent,
  useAuiState,
} from "@assistant-ui/react";
import {
  ArrowDownIcon,
  ArrowUpIcon,
  CheckIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  CopyIcon,
  DownloadIcon,
  Globe2Icon,
  ImageIcon,
  LoaderCircleIcon,
  LayoutDashboardIcon,
  MicIcon,
  PencilIcon,
  PlusIcon,
  RefreshCwIcon,
  Share2Icon,
  SquareIcon,
  ThumbsDownIcon,
  ThumbsUpIcon,
} from "lucide-react";
import {
  createContext,
  useEffect,
  useContext,
  useMemo,
  useState,
  type ComponentType,
  type FC,
  type PropsWithChildren,
} from "react";

export type ThreadGroupPart = MessagePrimitive.GroupedParts.GroupPart;

/**
 * Optional component overrides for the thread. `AssistantMessage` and
 * `Welcome` replace whole sections; the remaining slots override how the
 * assistant message renders tool calls and part groups. A `ReasoningGroup`
 * override receives status metadata only: raw reasoning children are
 * intentionally withheld from the UI. Tool UIs registered by name (toolkit
 * `render`, `useAssistantDataUI`) take precedence over `ToolFallback`.
 */
export type ThreadComponents = {
  AssistantMessage?: ComponentType | undefined;
  Welcome?: ComponentType | undefined;
  ToolFallback?: ToolCallMessagePartComponent | undefined;
  ToolGroup?:
    | ComponentType<PropsWithChildren<{ group: ThreadGroupPart }>>
    | undefined;
  ReasoningGroup?:
    | ComponentType<PropsWithChildren<{ group: ThreadGroupPart }>>
    | undefined;
};

export type ThreadProps = {
  compact?: boolean | undefined;
  components?: ThreadComponents | undefined;
  onOpenAccount?: (() => void) | undefined;
  onOpenDesktop?: (() => void) | undefined;
  workspaceOpen?: boolean | undefined;
};

const EMPTY_COMPONENTS: ThreadComponents = {};

const ThreadComponentsContext =
  createContext<ThreadComponents>(EMPTY_COMPONENTS);
const ThreadCompactContext = createContext(false);
const ThreadNavigationContext = createContext<{
  onOpenAccount?: (() => void) | undefined;
  onOpenDesktop?: (() => void) | undefined;
  workspaceOpen?: boolean | undefined;
}>({});

const defaultAssistantPartGroup = groupPartByType({
  reasoning: ["group-chainOfThought", "group-reasoning"],
  "tool-call": ["group-chainOfThought", "group-tool"],
  "standalone-tool-call": [],
});

const PRODUCT_STAGE_TOOLS = new Set([
  "project_case_analysis",
  "technology_card_build",
  "price_candidates_apply",
  "price_candidates_verify",
  "estimate_engine_calculate",
  "estimate_verification",
]);

const groupAssistantPart: typeof defaultAssistantPartGroup = (
  part,
  context,
) => {
  if (
    part.type === "tool-call" &&
    (part.toolName === "present" ||
      part.toolName === "get_weather" ||
      PRODUCT_STAGE_TOOLS.has(part.toolName))
  ) {
    return [];
  }
  return defaultAssistantPartGroup(part, context);
};

const INVALID_GENERATIVE_UI_NODE = Object.freeze({
  $type: "__invalid_kolibri_component__",
});

const weatherPartFingerprint = (part: {
  args: unknown;
  result?: unknown;
}) => {
  try {
    return JSON.stringify({
      args: part.args,
      result: part.result,
    });
  } catch {
    return null;
  }
};

// Startup exposes a loading placeholder thread; treat it as a new chat so
// its welcome content can stay centered while the composer remains docked.
const isNewChatView = (s: AssistantState) =>
  s.thread.messages.length === 0 &&
  (!s.thread.isLoading || s.threads.isLoading);

export const Thread: FC<ThreadProps> = ({
  compact = false,
  components = EMPTY_COMPONENTS,
  onOpenAccount,
  onOpenDesktop,
  workspaceOpen = false,
}) => {
  return (
    <ThreadNavigationContext.Provider
      value={{ onOpenAccount, onOpenDesktop, workspaceOpen }}
    >
      <ThreadCompactContext.Provider value={compact}>
        <ThreadComponentsContext.Provider value={components}>
          <ThreadRoot />
        </ThreadComponentsContext.Provider>
      </ThreadCompactContext.Provider>
    </ThreadNavigationContext.Provider>
  );
};

const ThreadRoot: FC = () => {
  const { Welcome = ThreadWelcome } = useContext(ThreadComponentsContext);
  const compact = useContext(ThreadCompactContext);
  const isRunning = useAuiState((s) => s.thread.isRunning);

  return (
    <ThreadPrimitive.Root
      aria-busy={isRunning}
      data-mobile-layout={compact ? "true" : "false"}
      className="aui-root aui-thread-root bg-background @container flex h-full min-h-0 min-w-0 flex-col overflow-hidden"
      style={{
        ["--thread-max-width" as string]: "46rem",
        ["--composer-bg" as string]: "var(--color-background)",
        ["--composer-radius" as string]: "1.25rem",
        ["--composer-padding" as string]: "7px",
      }}
    >
      <ThreadPrimitive.Viewport
        turnAnchor="top"
        autoScroll={true}
        scrollToBottomOnInitialize={true}
        scrollToBottomOnRunStart={true}
        scrollToBottomOnThreadSwitch={true}
        data-slot="aui_thread-viewport"
        className="relative flex min-h-0 min-w-0 flex-1 flex-col overflow-x-hidden overflow-y-auto overscroll-contain scroll-smooth"
      >
        <div
          className="mx-auto flex min-h-full w-[calc(100%-1.5rem)] min-w-0 max-w-(--thread-max-width) flex-1 flex-col pt-4"
        >
          <AuiIf condition={isNewChatView}>
            <div
              data-slot="aui_empty-state"
              className="flex min-h-0 flex-1 items-center justify-center py-6"
            >
              <Welcome />
            </div>
          </AuiIf>

          <div
            data-slot="aui_message-group"
            role="log"
            aria-label="Диалог с Kolibri"
            aria-live="polite"
            aria-relevant="additions"
            aria-busy={isRunning}
            className="mb-14 flex min-w-0 flex-col gap-y-6 empty:hidden"
          >
            <ThreadPrimitive.Messages>
              {() => <ThreadMessage />}
            </ThreadPrimitive.Messages>
          </div>

          <ThreadPrimitive.ViewportFooter
            data-composer-placement="bottom"
            className="aui-thread-viewport-footer sticky bottom-0 z-10 mt-auto flex min-w-0 shrink-0 flex-col gap-3 overflow-visible rounded-t-(--composer-radius) bg-background pt-2 pb-[calc(0.75rem+env(safe-area-inset-bottom))] md:pb-[calc(1rem+env(safe-area-inset-bottom))]"
          >
            <ThreadScrollToBottom />
            <ThreadFollowupSuggestions />
            <AuiIf condition={(s) => s.thread.isRunning}>
              <RunProgressPill />
            </AuiIf>
            <AuiIf condition={(s) => isNewChatView(s) && s.composer.isEmpty}>
              <ThreadSuggestions />
            </AuiIf>
            <Composer />
          </ThreadPrimitive.ViewportFooter>
        </div>
      </ThreadPrimitive.Viewport>
    </ThreadPrimitive.Root>
  );
};

const ThreadMessage: FC = () => {
  const { AssistantMessage: AssistantMessageComponent = AssistantMessage } =
    useContext(ThreadComponentsContext);
  const role = useAuiState((s) => s.message.role);
  const isEditing = useAuiState((s) => s.message.composer.isEditing);

  if (isEditing) return <EditComposer />;
  if (role === "user") return <UserMessage />;
  if (role === "assistant") return <AssistantMessageComponent />;
  return null;
};

const ThreadScrollToBottom: FC = () => {
  return (
    <ThreadPrimitive.ScrollToBottom asChild>
      <TooltipIconButton
        tooltip="К последнему сообщению"
        variant="outline"
        className="aui-thread-scroll-to-bottom dark:border-border dark:bg-background dark:hover:bg-accent absolute -top-12 z-10 self-center rounded-full p-4 disabled:invisible"
      >
        <ArrowDownIcon />
      </TooltipIconButton>
    </ThreadPrimitive.ScrollToBottom>
  );
};

const RunProgressPill: FC = () => {
  return (
    <div
      role="status"
      aria-live="polite"
      className="border-border/70 bg-background text-muted-foreground mx-auto flex h-9 max-w-full items-center gap-2 rounded-full border px-4 text-xs shadow-[0_6px_20px_-14px_rgba(0,0,0,0.35)]"
    >
      <LoaderCircleIcon
        className="size-4 shrink-0 animate-spin text-[#339cff]"
        aria-hidden="true"
      />
      <span className="truncate">Kolibri выполняет задачу</span>
    </div>
  );
};

const ThreadWelcome: FC = () => {
  return (
    <div className="aui-thread-welcome-root mb-5 flex min-w-0 flex-col items-center px-2 text-center">
      <h1 className="aui-thread-welcome-message-inner text-2xl font-semibold tracking-tight sm:text-3xl">
        Здравствуйте, я Kolibri
      </h1>
      <p className="text-muted-foreground mt-2 max-w-xl text-sm leading-relaxed text-pretty sm:text-base">
        Опишите задачу — я соберу исходные данные, отмечу допущения и подготовлю
        проверяемый результат.
      </p>
    </div>
  );
};

const ThreadSuggestions: FC = () => {
  const identity = useIdentity();

  if (identity.status !== "authenticated") {
    return null;
  }

  return (
    <>
      <div
        className="aui-mobile-starter-actions hidden w-full min-w-0 flex-col"
        aria-label="Быстрые действия"
      >
        <ThreadPrimitive.Suggestion
          prompt="Создай изображение по моему описанию. Сначала уточни стиль, формат и назначение."
          send
          clearComposer
          className="aui-mobile-starter-action"
          aria-label="Создать изображение"
        >
          <ImageIcon aria-hidden="true" />
          <span>Создать изображение</span>
        </ThreadPrimitive.Suggestion>
        <ThreadPrimitive.Suggestion
          prompt="Помоги написать или отредактировать текст. Сначала уточни тип текста, аудиторию и желаемый результат."
          className="aui-mobile-starter-action"
          aria-label="Написать или отредактировать"
        >
          <PencilIcon aria-hidden="true" />
          <span>Напиши или отредактируй</span>
        </ThreadPrimitive.Suggestion>
        <ThreadPrimitive.Suggestion
          prompt="Найди актуальную информацию в интернете по моему запросу и приложи источники."
          className="aui-mobile-starter-action"
          aria-label="Искать в интернете"
        >
          <Globe2Icon aria-hidden="true" />
          <span>Искать в интернете</span>
        </ThreadPrimitive.Suggestion>
      </div>
      <div
        className="aui-thread-welcome-suggestions grid w-full min-w-0 grid-cols-2 gap-2"
        aria-label="Быстрый старт"
      >
      <ThreadPrimitive.Suggestion
        prompt="Подготовь предварительную смету по моему описанию объекта. Сначала выдели исходные данные и допущения."
        send
        clearComposer
        className="border-border/70 bg-muted/25 hover:bg-muted/55 focus-visible:ring-ring flex min-h-16 min-w-0 flex-col items-start justify-center rounded-xl border px-3 py-2.5 text-start transition-colors outline-none focus-visible:ring-2"
        aria-label="Рассчитать смету по описанию объекта"
      >
        <span className="text-foreground text-sm leading-snug font-medium">
          Рассчитать смету
        </span>
        <span className="text-muted-foreground mt-1 line-clamp-1 text-xs">
          По описанию объекта
        </span>
      </ThreadPrimitive.Suggestion>

      <ThreadPrimitive.Suggestion
        prompt="Составь план проекта: этапы, зависимости, сроки, риски и необходимые исходные данные."
        send
        clearComposer
        className="border-border/70 bg-muted/25 hover:bg-muted/55 focus-visible:ring-ring flex min-h-16 min-w-0 flex-col items-start justify-center rounded-xl border px-3 py-2.5 text-start transition-colors outline-none focus-visible:ring-2"
        aria-label="Спланировать проект от цели до результата"
      >
        <span className="text-foreground text-sm leading-snug font-medium">
          Спланировать проект
        </span>
        <span className="text-muted-foreground mt-1 line-clamp-1 text-xs">
          От цели до результата
        </span>
      </ThreadPrimitive.Suggestion>

      <ThreadPrimitive.Suggestion
        prompt="Помоги подготовить проектный документ. Уточни тип документа, назначение и обязательные реквизиты."
        send
        clearComposer
        className="border-border/70 bg-muted/25 hover:bg-muted/55 focus-visible:ring-ring flex min-h-16 min-w-0 flex-col items-start justify-center rounded-xl border px-3 py-2.5 text-start transition-colors outline-none focus-visible:ring-2"
        aria-label="Подготовить проектный документ"
      >
        <span className="text-foreground text-sm leading-snug font-medium">
          Подготовить документ
        </span>
        <span className="text-muted-foreground mt-1 line-clamp-1 text-xs">
          КП, договор или отчёт
        </span>
      </ThreadPrimitive.Suggestion>

      <ThreadPrimitive.Suggestion
        prompt="Проверь исходные данные и выводы: покажи источники, допущения, версии и недостающие доказательства."
        send
        clearComposer
        className="border-border/70 bg-muted/25 hover:bg-muted/55 focus-visible:ring-ring flex min-h-16 min-w-0 flex-col items-start justify-center rounded-xl border px-3 py-2.5 text-start transition-colors outline-none focus-visible:ring-2"
        aria-label="Проверить источники и доказательства"
      >
        <span className="text-foreground text-sm leading-snug font-medium">
          Проверить основания
        </span>
        <span className="text-muted-foreground mt-1 line-clamp-1 text-xs">
          Источники и доказательства
        </span>
      </ThreadPrimitive.Suggestion>
      </div>
    </>
  );
};

const Composer: FC = () => {
  const compact = useContext(ThreadCompactContext);
  const identity = useIdentity();
  const authenticated = identity.status === "authenticated";
  const composerDisabled =
    !authenticated ||
    identity.agentProfileSaving ||
    identity.modelSettingsSaving;
  const attachmentsSupported = useAuiState(
    (s) => s.thread.capabilities.attachments,
  );
  const attachmentsDisabled = !authenticated || !attachmentsSupported;

  return (
    <ComposerPrimitive.Root className="aui-composer-root relative flex w-full min-w-0 flex-col">
      <ComposerPrimitive.AttachmentDropzone
        asChild
        disabled={attachmentsDisabled}
      >
        <div
          data-slot="aui_composer-shell"
          className="border-border/65 data-[dragging=true]:border-ring focus-within:border-ring/45 dark:border-muted-foreground/15 flex w-full min-w-0 flex-col gap-2 rounded-(--composer-radius) border bg-(--composer-bg) p-(--composer-padding) shadow-[0_12px_36px_-24px_rgba(0,0,0,0.45),0_2px_8px_-4px_rgba(0,0,0,0.12)] transition-[border-color,box-shadow] focus-within:shadow-[0_16px_40px_-24px_rgba(0,0,0,0.5),0_3px_10px_-4px_rgba(0,0,0,0.14)] data-[dragging=true]:border-dashed data-[dragging=true]:bg-[color-mix(in_oklab,var(--color-accent)_50%,var(--color-background))] dark:shadow-none [&_.aui-composer-attachments]:flex-wrap [&_.aui-composer-attachments]:overflow-x-hidden"
        >
          <ComposerAttachments />
          <AttachmentErrorNotice />
          <ComposerPrimitive.Input
            placeholder={
              authenticated
                ? compact
                  ? "Спросить Chat..."
                  : "Спросите что угодно"
                : "Войдите в личный кабинет, чтобы написать Kolibri"
            }
            disabled={composerDisabled}
            className="aui-composer-input caret-primary placeholder:text-muted-foreground/80 max-h-36 min-h-12 w-full min-w-0 resize-none overflow-x-hidden bg-transparent px-1.5 py-1 text-[15px] outline-none"
            rows={1}
            autoFocus={!compact}
            enterKeyHint="send"
            aria-label="Сообщение для Kolibri"
          />
          <ComposerAction />
        </div>
      </ComposerPrimitive.AttachmentDropzone>
    </ComposerPrimitive.Root>
  );
};

const ComposerAction: FC = () => {
  const compact = useContext(ThreadCompactContext);
  const identity = useIdentity();
  const { onOpenAccount, onOpenDesktop, workspaceOpen } = useContext(
    ThreadNavigationContext,
  );
  const authenticated = identity.status === "authenticated";
  const attachmentsSupported = useAuiState(
    (s) => s.thread.capabilities.attachments,
  );
  const dictationSupported = useAuiState(
    (s) => s.thread.capabilities.dictation,
  );
  const composerEmpty = useAuiState((s) => s.composer.isEmpty);
  const attachmentsDisabled = !authenticated || !attachmentsSupported;
  const attachmentTooltip = !authenticated
    ? "Войдите, чтобы прикрепить файл"
    : attachmentsSupported
      ? "Прикрепить файл"
      : "Вложения пока недоступны";

  return (
    <div className="aui-composer-action-wrapper relative flex items-center justify-between">
      <div className="aui-composer-leading-actions flex min-w-0 items-center gap-1">
        <ComposerPrimitive.AddAttachment asChild>
          <TooltipIconButton
            tooltip={attachmentTooltip}
            side="bottom"
            type="button"
            variant="ghost"
            size="icon"
            disabled={attachmentsDisabled}
            className="aui-composer-add-attachment hover:bg-muted-foreground/15 dark:border-muted-foreground/15 dark:hover:bg-muted-foreground/30 size-7 rounded-full"
            aria-label={attachmentTooltip}
          >
            <PlusIcon
              className="aui-attachment-add-icon size-[18px] stroke-[1.7px]"
              aria-hidden="true"
            />
          </TooltipIconButton>
        </ComposerPrimitive.AddAttachment>
        {!compact && onOpenDesktop ? (
          <TooltipIconButton
            tooltip={
              workspaceOpen
                ? "Скрыть рабочую область"
                : "Открыть рабочий стол"
            }
            side="bottom"
            type="button"
            variant="ghost"
            size="icon"
            data-canvas-launcher="composer"
            className={cn(
              "aui-composer-open-desktop size-7 rounded-full",
              workspaceOpen && "bg-muted text-foreground",
            )}
            aria-label={
              workspaceOpen
                ? "Скрыть рабочую область"
                : "Открыть рабочий стол"
            }
            aria-pressed={workspaceOpen}
            onClick={onOpenDesktop}
          >
            <LayoutDashboardIcon className="size-[17px] stroke-[1.7px]" />
          </TooltipIconButton>
        ) : null}
        {authenticated && !compact ? (
          <AgentProfileSelector control="developer" />
        ) : null}
        {authenticated && compact ? (
          <div className="aui-composer-mobile-model min-w-0">
            <AgentProfileSelector />
          </div>
        ) : null}
      </div>
      <div className="aui-composer-trailing-actions flex items-center gap-1.5">
        {!authenticated && onOpenAccount ? (
          <Button
            type="button"
            size="sm"
            onClick={onOpenAccount}
            className="h-7 rounded-full px-3 text-[12px]"
          >
            Войти
          </Button>
        ) : null}
        {authenticated ? (
          <>
            {!compact ? (
              <>
                <AuiIf condition={(s) => s.thread.isRunning}>
                  <LoaderCircleIcon
                    className="text-muted-foreground size-4 animate-spin"
                    aria-hidden="true"
                  />
                </AuiIf>
                <AgentProfileSelector />
              </>
            ) : null}
            <AuiIf condition={(s) => s.thread.capabilities.dictation}>
              <AuiIf condition={(s) => s.composer.dictation == null}>
                <ComposerPrimitive.Dictate asChild>
                  <TooltipIconButton
                    tooltip="Голосовой ввод"
                    side="bottom"
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="aui-composer-dictate size-7 rounded-full"
                    aria-label="Начать голосовой ввод"
                  >
                    <MicIcon className="aui-composer-dictate-icon size-4" />
                  </TooltipIconButton>
                </ComposerPrimitive.Dictate>
              </AuiIf>
              <AuiIf condition={(s) => s.composer.dictation != null}>
                <ComposerPrimitive.StopDictation asChild>
                  <TooltipIconButton
                    tooltip="Остановить голосовой ввод"
                    side="bottom"
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="aui-composer-stop-dictation text-destructive size-7 rounded-full"
                    aria-label="Остановить голосовой ввод"
                  >
                    <SquareIcon className="aui-composer-stop-dictation-icon size-3.5 animate-pulse fill-current" />
                  </TooltipIconButton>
                </ComposerPrimitive.StopDictation>
              </AuiIf>
            </AuiIf>
            {compact && !dictationSupported ? (
              <TooltipIconButton
                tooltip="Голосовой ввод недоступен"
                side="bottom"
                type="button"
                variant="ghost"
                size="icon"
                disabled
                className="aui-composer-dictate aui-composer-dictate-fallback size-7 rounded-full"
                aria-label="Голосовой ввод недоступен"
              >
                <MicIcon className="aui-composer-dictate-icon size-4" />
              </TooltipIconButton>
            ) : null}
            <AuiIf condition={(s) => !s.thread.isRunning}>
              <ComposerPrimitive.Send asChild>
                <TooltipIconButton
                  tooltip="Отправить сообщение"
                  side="bottom"
                  type="button"
                  variant="default"
                  size="icon"
                  disabled={
                    composerEmpty ||
                    identity.agentProfileSaving ||
                    identity.modelSettingsSaving
                  }
                  className={cn(
                    "aui-composer-send size-7 rounded-full",
                    compact && composerEmpty && "aui-composer-send-empty",
                  )}
                  aria-label={
                    composerEmpty
                      ? "Введите сообщение, чтобы отправить"
                      : "Отправить сообщение"
                  }
                >
                  <ArrowUpIcon
                    className="aui-composer-send-icon size-4.5"
                    aria-hidden="true"
                  />
                </TooltipIconButton>
              </ComposerPrimitive.Send>
            </AuiIf>
            <AuiIf condition={(s) => s.thread.isRunning}>
              <ComposerPrimitive.Cancel asChild>
                <Button
                  type="button"
                  variant="default"
                  size="icon"
                  className="aui-composer-cancel size-7 rounded-full"
                  aria-label="Остановить ответ"
                >
                  <SquareIcon className="aui-composer-cancel-icon size-3.5 fill-current" />
                </Button>
              </ComposerPrimitive.Cancel>
            </AuiIf>
          </>
        ) : null}
      </div>
    </div>
  );
};

const AttachmentErrorNotice: FC = () => {
  const [message, setMessage] = useState<string | null>(null);
  const attachmentCount = useAuiState((s) => s.composer.attachments.length);

  useAuiEvent("composer.attachmentAddError", ({ reason }) => {
    if (reason === "not-accepted") {
      setMessage("Этот формат файла пока не поддерживается.");
      return;
    }
    if (reason === "no-adapter") {
      setMessage("Вложения пока недоступны.");
      return;
    }
    setMessage("Не удалось добавить файл. Повторите попытку.");
  });

  useEffect(() => {
    if (attachmentCount > 0) setMessage(null);
  }, [attachmentCount]);

  if (!message) return null;

  return (
    <p
      role="alert"
      className="text-destructive px-1.5 text-xs leading-relaxed"
    >
      {message}
    </p>
  );
};

const MessageError: FC = () => {
  return (
    <MessagePrimitive.Error>
      <ErrorPrimitive.Root
        className="aui-message-error-root border-destructive bg-destructive/10 text-destructive dark:bg-destructive/5 mt-2 rounded-md border p-3 text-sm dark:text-red-200"
        aria-label="Ошибка сообщения"
      >
        <ErrorPrimitive.Message className="aui-message-error-message line-clamp-2" />
      </ErrorPrimitive.Root>
    </MessagePrimitive.Error>
  );
};

const AssistantMessage: FC = () => {
  const {
    ToolFallback: ToolFallbackComponent = ToolFallback,
    ToolGroup,
    ReasoningGroup,
  } = useContext(ThreadComponentsContext);

  const ACTION_BAR_PT = "pt-1.5";
  // Keep the action bar inside the contained root's paint box, then cancel its reserved space in flow.
  const ACTION_BAR_HEIGHT = `min-h-7.5 ${ACTION_BAR_PT}`;
  const currentMessageId = useAuiState((s) => s.message.id);
  const messageContent = useAuiState((s) => s.message.content);
  const threadMessages = useAuiState((s) => s.thread.messages);
  const hiddenWeatherToolCallIds = useMemo(() => {
    const seenFingerprints = new Set<string>();
    const hiddenIds = new Set<string>();
    const currentMessageIndex = threadMessages.findIndex(
      (message) => message.id === currentMessageId,
    );

    for (let index = currentMessageIndex - 1; index >= 0; index -= 1) {
      const message = threadMessages[index];
      if (message.role === "user") break;
      if (message.role !== "assistant") continue;
      for (const contentPart of message.content) {
        if (
          contentPart.type !== "tool-call" ||
          contentPart.toolName !== "get_weather"
        ) {
          continue;
        }
        const fingerprint = weatherPartFingerprint(contentPart);
        if (fingerprint) seenFingerprints.add(fingerprint);
      }
    }

    for (const contentPart of messageContent) {
      if (
        contentPart.type !== "tool-call" ||
        contentPart.toolName !== "get_weather"
      ) {
        continue;
      }
      const fingerprint = weatherPartFingerprint(contentPart);
      if (!fingerprint) continue;
      if (seenFingerprints.has(fingerprint)) {
        hiddenIds.add(contentPart.toolCallId);
      } else {
        seenFingerprints.add(fingerprint);
      }
    }

    return hiddenIds;
  }, [currentMessageId, messageContent, threadMessages]);
  const hasVisibleContent = messageContent.some(
    (part) =>
      part.type !== "tool-call" ||
      part.toolName !== "get_weather" ||
      !hiddenWeatherToolCallIds.has(part.toolCallId),
  );
  const currentEstimate = readShareableEstimate(messageContent);
  const currentEstimateKey =
    currentEstimate?.documentId ?? currentEstimate?.projectId ?? null;
  const latestEstimateMessage = currentEstimateKey
    ? [...threadMessages].reverse().find((message) => {
        const candidate = readShareableEstimate(message.content);
        return (
          candidate !== null &&
          (candidate.documentId ?? candidate.projectId) === currentEstimateKey
        );
      })
    : null;
  const isLatestEstimateMessage =
    currentEstimate !== null && latestEstimateMessage?.id === currentMessageId;
  const hasRenderableContent = messageContent.some((part) => {
    if (part.type !== "tool-call") return true;
    if (
      part.toolName === "get_weather" &&
      hiddenWeatherToolCallIds.has(part.toolCallId)
    ) {
      return false;
    }
    if (
      part.toolName === "present" &&
      isRecord(part.args) &&
      part.args.$type === "EstimateEditor"
    ) {
      return isLatestEstimateMessage;
    }
    return true;
  });
  const hasActionBarContent = messageContent.some((part) => {
    if (part.type === "text") return part.text.trim().length > 0;
    if (part.type === "generative-ui") return true;
    if (part.type !== "tool-call") return false;
    if (part.toolName === "get_weather") {
      return !hiddenWeatherToolCallIds.has(part.toolCallId);
    }
    if (part.toolName !== "present") return false;
    if (
      isRecord(part.args) &&
      part.args.$type === "EstimateEditor"
    ) {
      return isLatestEstimateMessage;
    }
    return true;
  });

  if (!hasVisibleContent || !hasRenderableContent) return null;

  return (
    <MessagePrimitive.Root
      data-slot="aui_assistant-message-root"
      data-role="assistant"
      className="fade-in slide-in-from-bottom-1 animate-in relative -mb-7.5 min-w-0 max-w-full pb-7.5 duration-150 [contain-intrinsic-size:auto_200px] [content-visibility:auto]"
    >
      <div
        data-slot="aui_assistant-message-content"
        className="text-foreground min-w-0 max-w-full overflow-hidden text-[15px] leading-[1.55] wrap-break-word"
      >
        <MessagePrimitive.GroupedParts
          groupBy={groupAssistantPart}
        >
          {({ part, children }) => {
            switch (part.type) {
              case "group-chainOfThought":
                return (
                  <div
                    data-slot="aui_chain-of-thought"
                    className="min-w-0 max-w-full"
                  >
                    {children}
                  </div>
                );
              case "group-tool":
                if (ToolGroup) {
                  return <ToolGroup group={part}>{children}</ToolGroup>;
                }
                return (
                  <ToolGroupRoot variant="ghost">
                    <ToolGroupTrigger
                      count={part.indices.length}
                      active={part.status.type === "running"}
                    />
                    <ToolGroupContent>{children}</ToolGroupContent>
                  </ToolGroupRoot>
                );
              case "group-reasoning": {
                // Reasoning payloads may contain hidden chain-of-thought. Keep
                // their lifecycle visible without ever placing raw text in the
                // rendered tree.
                if (ReasoningGroup) {
                  return <ReasoningGroup group={part} />;
                }
                const running = part.status.type === "running";
                return (
                  <ReasoningRoot
                    data-slot="aui_safe-reasoning-status"
                    streaming={running}
                    variant="ghost"
                    className="my-1.5"
                  >
                    <ReasoningTrigger
                      active={running}
                      label={
                        running ? "Kolibri выполняет задачу" : "Ход выполнения"
                      }
                    />
                    <ReasoningContent
                      role="status"
                      aria-live="polite"
                      aria-busy={running}
                    >
                      <ReasoningText>
                        <div className="space-y-2">
                          <div className="flex items-center gap-2">
                            <CheckIcon className="size-3.5 shrink-0 text-emerald-600" />
                            <span>Запрос принят и связан с текущим проектом</span>
                          </div>
                          <div className="flex items-center gap-2">
                            {running ? (
                              <LoaderCircleIcon className="size-3.5 shrink-0 animate-spin text-sky-600" />
                            ) : (
                              <CheckIcon className="size-3.5 shrink-0 text-emerald-600" />
                            )}
                            <span>
                              {running
                                ? "Готовится проверяемый результат"
                                : "Результат подготовлен"}
                            </span>
                          </div>
                        </div>
                      </ReasoningText>
                    </ReasoningContent>
                  </ReasoningRoot>
                );
              }
              case "text":
                return <MarkdownText />;
              case "reasoning":
                return null;
              case "generative-ui": {
                const parsed = parseNativeKolibriGenerativeUI(part.spec);
                return (
                  <KolibriGenerativeUI
                    node={
                      parsed.ok ? parsed.value : INVALID_GENERATIVE_UI_NODE
                    }
                    status={
                      part.status.type === "running" ? "streaming" : "done"
                    }
                  />
                );
              }
              case "tool-call":
                if (
                  part.toolName === "get_weather" &&
                  hiddenWeatherToolCallIds.has(part.toolCallId)
                ) {
                  return null;
                }
                if (part.toolName === "present") {
                  return (
                    <KolibriGenerativeUI
                      node={part.args}
                      status={
                        part.status.type === "running" ? "streaming" : "done"
                      }
                    />
                  );
                }
                return part.toolUI ?? <ToolFallbackComponent {...part} />;
              case "data":
                return part.dataRendererUI;
              case "indicator":
                return (
                  <span
                    data-slot="aui_assistant-message-indicator"
                    className="animate-pulse font-sans"
                    aria-label="Kolibri работает"
                  >
                    {"●"}
                  </span>
                );
              default:
                return null;
            }
          }}
        </MessagePrimitive.GroupedParts>
        <MessageError />
      </div>

      {hasActionBarContent ? (
        <div
          data-slot="aui_assistant-message-footer"
          className={cn("ms-2 flex items-center", ACTION_BAR_HEIGHT)}
        >
          <BranchPicker />
          <AssistantActionBar />
        </div>
      ) : null}
    </MessagePrimitive.Root>
  );
};

const AssistantActionBar: FC = () => {
  return (
    <ActionBarPrimitive.Root
      hideWhenRunning
      autohide="never"
      className="aui-assistant-action-bar-root text-muted-foreground animate-in fade-in col-start-3 row-start-2 -ms-1 flex gap-1 duration-200"
    >
      <AuiIf
        condition={(s) =>
          s.message.content.some(
            (part) => part.type === "text" && part.text.trim().length > 0,
          )
        }
      >
        <ActionBarPrimitive.Copy asChild>
          <TooltipIconButton tooltip="Копировать">
            <AuiIf condition={(s) => s.message.isCopied}>
              <CheckIcon className="animate-in zoom-in-50 fade-in duration-200 ease-out" />
            </AuiIf>
            <AuiIf condition={(s) => !s.message.isCopied}>
              <CopyIcon className="animate-in zoom-in-75 fade-in duration-150" />
            </AuiIf>
          </TooltipIconButton>
        </ActionBarPrimitive.Copy>
      </AuiIf>
      <ActionBarPrimitive.FeedbackPositive asChild>
        <TooltipIconButton
          tooltip="Хороший ответ"
          className="data-[submitted=true]:bg-accent data-[submitted=true]:text-foreground"
        >
          <ThumbsUpIcon />
        </TooltipIconButton>
      </ActionBarPrimitive.FeedbackPositive>
      <ActionBarPrimitive.FeedbackNegative asChild>
        <TooltipIconButton
          tooltip="Плохой ответ"
          className="data-[submitted=true]:bg-accent data-[submitted=true]:text-foreground"
        >
          <ThumbsDownIcon />
        </TooltipIconButton>
      </ActionBarPrimitive.FeedbackNegative>
      <ActionBarPrimitive.Reload asChild>
        <TooltipIconButton tooltip="Повторить ответ">
          <RefreshCwIcon />
        </TooltipIconButton>
      </ActionBarPrimitive.Reload>
      <AssistantMessageShareAction />
      <AssistantMessageDownloadAction />
      <MessageTime />
      <MessageTiming side="bottom" />
    </ActionBarPrimitive.Root>
  );
};

type ShareableEstimate = {
  documentId: string | null;
  projectId: string;
  version: number;
  title: string;
  region: string | null;
  total: string | null;
};

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const readShareableEstimate = (
  content: readonly {
    type: string;
    [key: string]: unknown;
  }[],
): ShareableEstimate | null => {
  for (const part of content) {
    if (
      part.type !== "tool-call" ||
      part.toolName !== "present" ||
      !isRecord(part.args) ||
      part.args.$type !== "EstimateEditor" ||
      typeof part.args.projectId !== "string" ||
      typeof part.args.version !== "number"
    ) {
      continue;
    }

    const totals = isRecord(part.args.totals) ? part.args.totals : null;
    const rawTotal = totals?.total;
    return {
      documentId:
        typeof part.args.documentId === "string"
          ? part.args.documentId
          : null,
      projectId: part.args.projectId,
      version: part.args.version,
      title:
        typeof part.args.estimateTitle === "string"
          ? part.args.estimateTitle
          : "Смета Kolibri",
      region:
        typeof part.args.estimateRegion === "string"
          ? part.args.estimateRegion
          : null,
      total:
        typeof rawTotal === "string" || typeof rawTotal === "number"
          ? String(rawTotal)
          : null,
    };
  }
  return null;
};

const AssistantMessageShareAction: FC = () => {
  const text = useAuiState((state) =>
    state.message.content
      .filter(
        (part): part is Extract<typeof part, { type: "text" }> =>
          part.type === "text",
      )
      .map((part) => part.text)
      .join("\n\n")
      .trim(),
  );
  const estimateJson = useAuiState((state) =>
    JSON.stringify(readShareableEstimate(state.message.content)),
  );
  const estimate = useMemo(
    () => JSON.parse(estimateJson) as ShareableEstimate | null,
    [estimateJson],
  );
  const isCurrentEstimate = useAuiState((state) => {
    const current = readShareableEstimate(state.message.content);
    if (!current) return true;
    const currentKey = current.documentId ?? current.projectId;
    const latest = [...state.thread.messages]
      .reverse()
      .find((message) => {
        const candidate = readShareableEstimate(message.content);
        return (
          candidate !== null &&
          (candidate.documentId ?? candidate.projectId) === currentKey
        );
      });
    return latest?.id === state.message.id;
  });
  const [completed, setCompleted] = useState(false);
  const [preparing, setPreparing] = useState(false);
  const [statusMessage, setStatusMessage] = useState("");
  const [visibleError, setVisibleError] = useState("");

  const share = async () => {
    setVisibleError("");
    try {
      if (estimate) {
        setPreparing(true);
        setStatusMessage("Готовлю PDF…");
        const prepared = await prepareEstimateShareFiles(
          estimate.projectId,
          estimate.version,
        );
        setStatusMessage("Открываю системное меню отправки…");
        const result = await sharePreparedEstimateFiles(prepared, {
          title: estimate.title,
          text: [
            estimate.title,
            estimate.region ? `Регион: ${estimate.region}` : null,
            estimate.total ? `Итого: ${estimate.total}` : null,
            "PDF, Excel и Word сформированы из одной версии сметы.",
          ]
            .filter((line): line is string => Boolean(line))
            .join("\n"),
        });
        setStatusMessage(shareResultMessage(result));
        if (result.status !== "shared") {
          if (result.status === "unsupported") {
            setVisibleError(
              "Этот браузер не поддерживает системную отправку PDF.",
            );
          }
          return;
        }
        setCompleted(true);
        window.setTimeout(() => setCompleted(false), 1_800);
        return;
      }

      if (typeof navigator.share === "function") {
        await navigator.share({
          title: "Ответ Kolibri",
          text,
        });
      } else {
        await navigator.clipboard.writeText(text);
      }
      setCompleted(true);
      window.setTimeout(() => setCompleted(false), 1_800);
    } catch (error: unknown) {
      if (error instanceof DOMException && error.name === "AbortError") return;
      if (estimate) {
        const message =
          error instanceof Error
            ? error.message
            : "Не удалось открыть системное меню отправки.";
        setStatusMessage(message);
        setVisibleError(message);
        return;
      }
      try {
        await navigator.clipboard.writeText(text);
        setCompleted(true);
        window.setTimeout(() => setCompleted(false), 1_800);
      } catch {
        // The browser denied both system share and clipboard access.
      }
    } finally {
      setPreparing(false);
    }
  };

  if ((!text && !estimate) || (estimate && !isCurrentEstimate)) return null;

  return (
    <span className="relative inline-flex">
      <TooltipIconButton
        tooltip={
          completed
            ? estimate
              ? "Смета передана"
              : "Ответ передан"
            : statusMessage ||
              (estimate ? "Поделиться сметой" : "Поделиться ответом")
        }
        aria-label={
          estimate ? "Поделиться сметой" : "Поделиться ответом"
        }
        disabled={preparing}
        onClick={() => void share()}
      >
        {preparing ? (
          <LoaderCircleIcon className="animate-spin" />
        ) : completed ? (
          <CheckIcon />
        ) : (
          <Share2Icon />
        )}
      </TooltipIconButton>
      {visibleError ? (
        <span
          role="alert"
          className="border-border bg-background text-foreground absolute bottom-full left-0 z-30 mb-2 w-64 rounded-lg border px-3 py-2 text-xs leading-relaxed shadow-lg"
        >
          {visibleError}
        </span>
      ) : null}
    </span>
  );
};

const AssistantMessageDownloadAction: FC = () => {
  const estimateJson = useAuiState((state) =>
    JSON.stringify(readShareableEstimate(state.message.content)),
  );
  const estimate = useMemo(
    () => JSON.parse(estimateJson) as ShareableEstimate | null,
    [estimateJson],
  );

  if (!estimate) {
    return (
      <ActionBarPrimitive.ExportMarkdown asChild>
        <TooltipIconButton tooltip="Скачать ответ в Markdown">
          <DownloadIcon />
        </TooltipIconButton>
      </ActionBarPrimitive.ExportMarkdown>
    );
  }

  return (
    <TooltipIconButton
      tooltip="Скачать смету в PDF"
      aria-label="Скачать смету в PDF"
      onClick={() => {
        const anchor = document.createElement("a");
        anchor.href = `/api/v3/projects/${encodeURIComponent(
          estimate.projectId,
        )}/estimate/export/pdf`;
        anchor.download = "";
        anchor.rel = "noopener";
        document.body.append(anchor);
        anchor.click();
        anchor.remove();
      }}
    >
      <DownloadIcon />
    </TooltipIconButton>
  );
};

const UserMessage: FC = () => {
  return (
    <MessagePrimitive.Root
      data-slot="aui_user-message-root"
      className="group/user fade-in slide-in-from-bottom-1 animate-in flex min-w-0 max-w-full flex-col items-end gap-y-1.5 duration-150 [contain-intrinsic-size:auto_200px] [content-visibility:auto] [&_.aui-user-message-attachments-end]:max-w-[78%] [&_.aui-user-message-attachments-end]:flex-wrap"
      data-role="user"
    >
      <UserMessageAttachments />

      <div className="aui-user-message-content-wrapper relative w-fit max-w-[78%] min-w-0">
        <div className="aui-user-message-content peer bg-[#f3f3f4] text-foreground rounded-2xl px-4 py-2 text-[15px] leading-[1.45] wrap-break-word empty:hidden dark:bg-zinc-800">
          <MessagePrimitive.Parts />
        </div>
      </div>

      <div className="text-muted-foreground flex min-h-5 items-center justify-end gap-1 text-[11px]">
        <MessageTime />
        <UserActionBar />
      </div>

      <BranchPicker
        data-slot="aui_user-branch-picker"
        className="-me-1 justify-end"
      />
    </MessagePrimitive.Root>
  );
};

const UserActionBar: FC = () => {
  return (
    <ActionBarPrimitive.Root className="aui-user-action-bar-root flex items-center">
      <ActionBarPrimitive.Copy asChild>
        <TooltipIconButton
          tooltip="Копировать"
          className="aui-user-action-copy size-6 rounded-md"
        >
          <AuiIf condition={(s) => s.message.isCopied}>
            <CheckIcon className="size-3.5" />
          </AuiIf>
          <AuiIf condition={(s) => !s.message.isCopied}>
            <CopyIcon className="size-3.5" />
          </AuiIf>
        </TooltipIconButton>
      </ActionBarPrimitive.Copy>
      <ActionBarPrimitive.Edit asChild>
        <TooltipIconButton
          tooltip="Редактировать"
          className="aui-user-action-edit size-6 rounded-md opacity-0 transition-opacity group-hover/user:opacity-100 focus-visible:opacity-100"
        >
          <PencilIcon className="size-3.5" />
        </TooltipIconButton>
      </ActionBarPrimitive.Edit>
    </ActionBarPrimitive.Root>
  );
};

const MessageTime: FC = () => {
  const createdAt = useAuiState((s) => s.message.createdAt);
  if (!createdAt) return null;

  const date =
    createdAt instanceof Date ? createdAt : new Date(createdAt as string);
  if (Number.isNaN(date.getTime())) return null;

  return (
    <time dateTime={date.toISOString()} className="tabular-nums">
      {date.toLocaleTimeString("ru-RU", {
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      })}
    </time>
  );
};

const EditComposer: FC = () => {
  return (
    <MessagePrimitive.Root
      data-slot="aui_edit-composer-wrapper"
      className="flex flex-col px-2 [contain-intrinsic-size:auto_200px] [content-visibility:auto]"
    >
      <ComposerPrimitive.Root className="aui-edit-composer-root border-border/60 dark:border-muted-foreground/15 ms-auto flex w-full max-w-[85%] flex-col rounded-(--composer-radius) border bg-(--composer-bg) shadow-[0_4px_16px_-8px_rgba(0,0,0,0.08),0_1px_2px_rgba(0,0,0,0.04)] dark:shadow-none">
        <ComposerPrimitive.Input
          className="aui-edit-composer-input text-foreground min-h-14 w-full resize-none bg-transparent px-4 pt-3 pb-1 text-base outline-none"
          autoFocus
        />
        <div className="aui-edit-composer-footer mx-2.5 mb-2.5 flex items-center gap-1.5 self-end">
          <ComposerPrimitive.Cancel asChild>
            <Button
              variant="ghost"
              size="sm"
              className="h-8 rounded-full px-3.5"
            >
              Отмена
            </Button>
          </ComposerPrimitive.Cancel>
          <ComposerPrimitive.Send asChild>
            <Button size="sm" className="h-8 rounded-full px-3.5">
              Сохранить
            </Button>
          </ComposerPrimitive.Send>
        </div>
      </ComposerPrimitive.Root>
    </MessagePrimitive.Root>
  );
};

const BranchPicker: FC<BranchPickerPrimitive.Root.Props> = ({
  className,
  ...rest
}) => {
  return (
    <BranchPickerPrimitive.Root
      hideWhenSingleBranch
      className={cn(
        "aui-branch-picker-root text-muted-foreground -ms-2 me-2 inline-flex items-center text-xs",
        className,
      )}
      {...rest}
    >
      <BranchPickerPrimitive.Previous asChild>
        <TooltipIconButton tooltip="Предыдущая версия">
          <ChevronLeftIcon />
        </TooltipIconButton>
      </BranchPickerPrimitive.Previous>
      <span className="aui-branch-picker-state font-medium">
        <BranchPickerPrimitive.Number /> / <BranchPickerPrimitive.Count />
      </span>
      <BranchPickerPrimitive.Next asChild>
        <TooltipIconButton tooltip="Следующая версия">
          <ChevronRightIcon />
        </TooltipIconButton>
      </BranchPickerPrimitive.Next>
    </BranchPickerPrimitive.Root>
  );
};
