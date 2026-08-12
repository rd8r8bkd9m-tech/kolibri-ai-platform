"use client";

import {
	AuiIf,
	ComposerPrimitive,
	QueueItemPrimitive,
	ThreadPrimitive,
	useAuiEvent,
	useAuiState,
} from "@assistant-ui/react";
import {
	ArrowDownIcon,
	ArrowUpIcon,
	LoaderCircleIcon,
	MicIcon,
	PanelRightIcon,
	PlusIcon,
	SquareIcon,
} from "lucide-react";
import { type ComponentType, useContext, useEffect, useState } from "react";
import { AgentProfileSelector } from "@/components/assistant-ui/agent-profile-selector";
import { ComposerAttachments } from "@/components/assistant-ui/attachment";
import { KolibriComposerTriggers } from "@/components/assistant-ui/composer/kolibri-composer-triggers";
import { TooltipIconButton } from "@/components/assistant-ui/tooltip-icon-button";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { uiClassTokens } from "@/components/ui/class-names";
import { useIdentity } from "@/lib/identity/provider";
import {
	ThreadCompactContext,
	ThreadComponentsContext,
	ThreadNavigationContext,
} from "../thread-context";
import {
	THREAD_UI_CLASS,
	THREAD_UI_TEXT,
} from "../thread-ui-constants";
import {
	AssistantMessage,
	EditComposer,
	UserMessage,
} from "./thread-message";
import {
	DESKTOP_STARTERS,
	MOBILE_STARTERS,
} from "../thread-suggestions-config";

export const ThreadMessage: ComponentType = () => {
	const { AssistantMessage: AssistantMessageComponent = AssistantMessage } =
		useContext(ThreadComponentsContext);
	const role = useAuiState((s) => s.message.role);
	const isEditing = useAuiState((s) => s.message.composer.isEditing);

	if (isEditing) return <EditComposer />;
	if (role === "user") return <UserMessage />;
	if (role === "assistant") return <AssistantMessageComponent />;
	return null;
};

export const ThreadScrollToBottom: ComponentType = () => {
	return (
				<ThreadPrimitive.ScrollToBottom asChild>
				<TooltipIconButton
					tooltip={THREAD_UI_TEXT.TOOLTIP_SCROLL_TO_BOTTOM}
					variant="outline"
					className={uiClassTokens.threadScrollToBottom}
				>
					<ArrowDownIcon />
				</TooltipIconButton>
		</ThreadPrimitive.ScrollToBottom>
	);
};

export const RunProgressPill: ComponentType = () => {
	return (
		<div
			role="status"
			aria-live="polite"
			className={uiClassTokens.threadRunProgressPill}
		>
				<LoaderCircleIcon className={THREAD_UI_CLASS.SPINNER_RUNNING} />
				<span className="truncate">{THREAD_UI_TEXT.RUN_PROGRESS_TEXT}</span>
		</div>
	);
};

export const ThreadWelcome: ComponentType = () => {
	return (
		<div className={uiClassTokens.threadWelcomeRoot}>
			<h1 className={uiClassTokens.threadWelcomeTitle}>
				{THREAD_UI_TEXT.WELCOME_TITLE}
			</h1>
			<p className={uiClassTokens.threadWelcomeText}>
				{THREAD_UI_TEXT.WELCOME_SUBTITLE}
			</p>
		</div>
	);
};

export const ThreadSuggestions: ComponentType = () => {
	const identity = useIdentity();

	if (identity.status !== "authenticated") {
		return null;
	}
	const desktopStarters = identity.user?.capabilities.includes(
		"construction.estimates.workspace",
	)
		? DESKTOP_STARTERS
		: DESKTOP_STARTERS.filter(({ title }) => title !== "Рассчитать смету");

	return (
		<>
			<div
				className={uiClassTokens.threadMobileStarterActions}
				aria-label={THREAD_UI_TEXT.THREAD_MOBILE_ACTIONS_ARIA}
			>
				{MOBILE_STARTERS.map(({ icon: Icon, label, prompt, send }) => (
					<ThreadPrimitive.Suggestion
						key={label}
						prompt={prompt}
						send={send}
						clearComposer={send}
					className={THREAD_UI_CLASS.MOBILE_STARTER_BADGE}
					aria-label={label}
					>
						<Icon aria-hidden="true" />
						<span>{label}</span>
					</ThreadPrimitive.Suggestion>
				))}
			</div>
			<div
					className={uiClassTokens.threadWelcomeSuggestions}
					aria-label={THREAD_UI_TEXT.THREAD_VIEWPORT_WELCOME_LABEL}
				>
				{desktopStarters.map(({ ariaLabel, description, prompt, title }) => (
					<ThreadPrimitive.Suggestion
						key={title}
						prompt={prompt}
						send
						clearComposer
						className={uiClassTokens.threadWelcomeSuggestionCard}
						aria-label={ariaLabel}
					>
						<span className={uiClassTokens.threadWelcomeSuggestionTitle}>
							{title}
						</span>
						<span className={uiClassTokens.threadWelcomeSuggestionDescription}>
							{description}
						</span>
					</ThreadPrimitive.Suggestion>
				))}
			</div>
		</>
	);
};

export const AttachmentErrorNotice: ComponentType = () => {
	const [message, setMessage] = useState<string | null>(null);
	const attachmentCount = useAuiState((s) => s.composer.attachments.length);

	useAuiEvent("composer.attachmentAddError", ({ reason }) => {
		if (reason === "not-accepted") {
			setMessage(THREAD_UI_TEXT.THREAD_COMPOSER_ATTACHMENT_ERROR_NOT_ACCEPTED);
			return;
		}
		if (reason === "no-adapter") {
			setMessage(THREAD_UI_TEXT.THREAD_COMPOSER_ATTACHMENT_ERROR_NO_ADAPTER);
			return;
		}
		setMessage(THREAD_UI_TEXT.THREAD_COMPOSER_ATTACHMENT_ERROR_TYPE);
	});

	useEffect(() => {
		if (attachmentCount > 0) setMessage(null);
	}, [attachmentCount]);

	if (!message) return null;

	return (
		<p role="alert" className={THREAD_UI_CLASS.THREAD_COMPOSER_ERROR_ALERT}>
				{message}
			</p>
		);
	};

export const Composer: ComponentType = () => {
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
		<ComposerPrimitive.Unstable_TriggerPopoverRoot>
			<ComposerPrimitive.Root className={uiClassTokens.threadComposerRoot}>
				<ComposerPrimitive.AttachmentDropzone
					asChild
					disabled={attachmentsDisabled}
					>
					<div
						data-slot="aui_composer-shell"
						className={uiClassTokens.threadComposerShell}
					>
						<ComposerAttachments />
						<AttachmentErrorNotice />
						<ComposerPrimitive.Quote className="border-border bg-muted/35 mx-3 mt-2 flex items-center gap-2 rounded-md border px-2 py-1 text-xs">
							<ComposerPrimitive.QuoteText className="min-w-0 flex-1 truncate" />
							<ComposerPrimitive.QuoteDismiss
								asChild
								aria-label="Убрать цитату"
							>
								<button type="button" className="rounded px-1 hover:bg-muted">×</button>
							</ComposerPrimitive.QuoteDismiss>
						</ComposerPrimitive.Quote>
						<div className="mx-3 mt-2 space-y-1" aria-label="Очередь сообщений">
							<ComposerPrimitive.Queue>
								{({ queueItem }) => (
									<div key={queueItem.id} className="border-border bg-muted/25 flex items-center gap-2 rounded-md border px-2 py-1 text-xs">
										<QueueItemPrimitive.Text className="min-w-0 flex-1 truncate" />
										<QueueItemPrimitive.Steer asChild>
											<button type="button" className="rounded px-1.5 py-0.5 hover:bg-muted">Сейчас</button>
										</QueueItemPrimitive.Steer>
										<QueueItemPrimitive.Remove asChild>
											<button type="button" className="rounded px-1.5 py-0.5 text-muted-foreground hover:bg-muted">Убрать</button>
										</QueueItemPrimitive.Remove>
									</div>
								)}
							</ComposerPrimitive.Queue>
						</div>
						<ComposerPrimitive.Input
										placeholder={
											authenticated
												? compact
													? THREAD_UI_TEXT.TOOLTIP_MOBILE_HINT
													: THREAD_UI_TEXT.DRAFT_AUTH
												: THREAD_UI_TEXT.THREAD_VIEWPORT_LOGIN_REQUIRED
												}
							disabled={composerDisabled}
							className={uiClassTokens.threadComposerInput}
							rows={1}
							autoFocus={!compact}
							enterKeyHint="send"
							aria-label={THREAD_UI_TEXT.THREAD_INPUT_ARIA_LABEL}
						/>
						<KolibriComposerTriggers />
						<ComposerAction />
					</div>
				</ComposerPrimitive.AttachmentDropzone>
			</ComposerPrimitive.Root>
		</ComposerPrimitive.Unstable_TriggerPopoverRoot>
	);
};

export const ComposerAction: ComponentType = () => {
	const compact = useContext(ThreadCompactContext);
	const identity = useIdentity();
	const { onOpenAccount, onOpenContextPanel, workspaceOpen } =
		useContext(ThreadNavigationContext);
	const authenticated = identity.status === "authenticated";
	const attachmentsSupported = useAuiState((s) => s.thread.capabilities.attachments);
	const attachmentsDisabled = !authenticated || !attachmentsSupported;
	const attachmentTooltip = !authenticated
		? THREAD_UI_TEXT.TOOLTIP_ATTACH
		: attachmentsSupported
			? THREAD_UI_TEXT.TOOLTIP_ATTACH_ENABLED
			: THREAD_UI_TEXT.TOOLTIP_ATTACH_DISABLED;

	return (
		<div className={uiClassTokens.threadComposerActionRow}>
			<div className={uiClassTokens.threadComposerLeadingActions}>
				<ComposerPrimitive.AddAttachment asChild>
					<TooltipIconButton
						tooltip={attachmentTooltip}
						side="bottom"
						type="button"
						variant="ghost"
						size="icon"
						disabled={attachmentsDisabled}
						className={cn(
							"aui-composer-add-attachment hover:bg-muted-foreground/15 dark:border-muted-foreground/15 dark:hover:bg-muted-foreground/30",
							uiClassTokens.threadActionButton,
						)}
						aria-label={attachmentTooltip}
					>
						<PlusIcon
							className={cn(
								"aui-attachment-add-icon",
								uiClassTokens.threadActionIcon,
							)}
							aria-hidden="true"
						/>
					</TooltipIconButton>
				</ComposerPrimitive.AddAttachment>
				{!compact && onOpenContextPanel ? (
					<TooltipIconButton
					tooltip={
						workspaceOpen
							? THREAD_UI_TEXT.LABEL_CONTEXT_CLOSE
							: THREAD_UI_TEXT.LABEL_CONTEXT_OPEN
					}
						side="bottom"
						type="button"
						variant="ghost"
						size="icon"
						data-context-launcher="composer"
						aria-controls="workspace-canvas"
						className={cn(
							"aui-composer-open-context",
							uiClassTokens.threadActionButton,
							workspaceOpen && "bg-muted text-foreground",
						)}
						aria-label={
							workspaceOpen
								? THREAD_UI_TEXT.LABEL_CONTEXT_CLOSE
								: THREAD_UI_TEXT.LABEL_CONTEXT_OPEN
						}
						aria-pressed={workspaceOpen}
						onClick={onOpenContextPanel}
					>
						<PanelRightIcon className={uiClassTokens.threadActionIcon} />
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
			<div className={uiClassTokens.threadComposerTrailingActions}>
								{!authenticated && onOpenAccount ? (
									<Button
										type="button"
										size="sm"
										onClick={onOpenAccount}
									className="h-7 rounded-full px-3 text-[12px]"
								>
									{THREAD_UI_TEXT.LABEL_OPEN_ACCOUNT}
								</Button>
								) : null}
				{authenticated ? (
					<>
						{!compact ? (
							<AgentProfileSelector />
						) : null}
						<AuiIf condition={(s) => s.thread.capabilities.dictation}>
							<AuiIf condition={(s) => s.composer.dictation == null}>
								<ComposerPrimitive.Dictate asChild>
										<TooltipIconButton
											tooltip={THREAD_UI_TEXT.TOOLTIP_DICTATE}
										side="bottom"
										type="button"
										variant="ghost"
										size="icon"
										className={uiClassTokens.threadActionButton}
											aria-label={THREAD_UI_TEXT.LABEL_COMPOSE_DICTATE}
									>
										<MicIcon className={uiClassTokens.threadDictateIcon} />
									</TooltipIconButton>
								</ComposerPrimitive.Dictate>
							</AuiIf>
							<AuiIf condition={(s) => s.composer.dictation != null}>
								<ComposerPrimitive.StopDictation asChild>
										<TooltipIconButton
											tooltip={THREAD_UI_TEXT.TOOLTIP_DICTATE_STOP}
										side="bottom"
										type="button"
										variant="ghost"
										size="icon"
										className={cn(
											uiClassTokens.threadActionButton,
											"aui-composer-stop-dictation text-destructive",
										)}
											aria-label={THREAD_UI_TEXT.LABEL_COMPOSE_DICTATE_STOP}
									>
										<SquareIcon className="aui-composer-stop-dictation-icon size-3.5 animate-pulse fill-current" />
									</TooltipIconButton>
								</ComposerPrimitive.StopDictation>
							</AuiIf>
						</AuiIf>
						<AuiIf condition={(s) => !s.thread.isRunning && !s.composer.isEmpty}>
							<ComposerPrimitive.Send asChild>
								<TooltipIconButton
									tooltip={THREAD_UI_TEXT.LABEL_COMPOSE_SEND}
									side="bottom"
									type="submit"
									variant="default"
									size="icon"
									disabled={
										identity.agentProfileSaving ||
										identity.modelSettingsSaving
									}
									className={cn(
										uiClassTokens.threadComposerSend,
									)}
									aria-label={THREAD_UI_TEXT.LABEL_COMPOSE_SEND}
								>
									<ArrowUpIcon className={uiClassTokens.threadDictateIcon} />
								</TooltipIconButton>
							</ComposerPrimitive.Send>
						</AuiIf>
						<AuiIf condition={(s) => s.thread.isRunning}>
							<ComposerPrimitive.Cancel asChild>
												<Button
													type="button"
													variant="default"
													size="icon"
													className={uiClassTokens.threadComposerCancel}
													aria-label={THREAD_UI_TEXT.TOOLTIP_CANCEL_STREAM}
												>
									<SquareIcon className={uiClassTokens.threadComposerCancelIcon} />
								</Button>
							</ComposerPrimitive.Cancel>
						</AuiIf>
					</>
				) : null}
			</div>
		</div>
	);
};
