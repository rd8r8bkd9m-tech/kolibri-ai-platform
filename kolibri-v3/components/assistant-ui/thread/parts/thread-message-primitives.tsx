"use client";

import {
	ActionBarPrimitive,
	AuiIf,
	BranchPickerPrimitive,
	ComposerPrimitive,
	ErrorPrimitive,
	MessagePrimitive,
	useAuiState,
} from "@assistant-ui/react";
import {
	CheckIcon,
	ChevronLeftIcon,
	ChevronRightIcon,
	CopyIcon,
	DownloadIcon,
	LoaderCircleIcon,
	Share2Icon,
	ThumbsDownIcon,
	ThumbsUpIcon,
	PencilIcon,
	RefreshCwIcon,
} from "lucide-react";
import { type ComponentType, useMemo, useState } from "react";
import { UserMessageAttachments } from "@/components/assistant-ui/attachment";
import { DirectiveText } from "@/components/assistant-ui/directive-text";
import { MessageTiming } from "@/components/assistant-ui/message-timing";
import {
	prepareEstimateShareFiles,
	sharePreparedEstimateFiles,
	shareResultMessage,
} from "@/lib/estimate-share";
import { cn } from "@/lib/utils";
import { TooltipIconButton } from "@/components/assistant-ui/tooltip-icon-button";
import { Button } from "@/components/ui/button";
import { uiClassTokens } from "@/components/ui/class-names";
import {
	readShareableEstimate,
	type ShareableEstimate,
} from "../thread-context";
import { THREAD_UI_CLASS, THREAD_UI_TEXT } from "../thread-ui-constants";

export const MessageTime: ComponentType = () => {
	const createdAt = useAuiState((s) => s.message.createdAt);
	if (!createdAt) return null;

	const date = createdAt instanceof Date ? createdAt : new Date(createdAt as string);
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

export const BranchPicker: ComponentType<
	BranchPickerPrimitive.Root.Props
> = ({ className, ...rest }) => {
	return (
		<BranchPickerPrimitive.Root
			hideWhenSingleBranch
			className={cn(uiClassTokens.threadBranchPicker, className)}
			{...rest}
		>
			<BranchPickerPrimitive.Previous asChild>
				<TooltipIconButton tooltip={THREAD_UI_TEXT.TOOLTIP_PREVIOUS_BRANCH}>
					<ChevronLeftIcon />
				</TooltipIconButton>
			</BranchPickerPrimitive.Previous>
			<span className={THREAD_UI_CLASS.THREAD_BRANCH_STATE_CLASS}>
				<BranchPickerPrimitive.Number /> / <BranchPickerPrimitive.Count />
			</span>
			<BranchPickerPrimitive.Next asChild>
				<TooltipIconButton tooltip={THREAD_UI_TEXT.TOOLTIP_NEXT_BRANCH}>
					<ChevronRightIcon />
				</TooltipIconButton>
			</BranchPickerPrimitive.Next>
		</BranchPickerPrimitive.Root>
	);
};

export const MessageError: ComponentType = () => {
	return (
		<MessagePrimitive.Error>
			<ErrorPrimitive.Root
				className={uiClassTokens.threadMessageError}
				aria-label={THREAD_UI_TEXT.MESSAGE_ERROR_LABEL}
			>
				<ErrorPrimitive.Message className={THREAD_UI_CLASS.THREAD_MESSAGE_ERROR_CLASS} />
			</ErrorPrimitive.Root>
		</MessagePrimitive.Error>
	);
};

export const UserActionBar: ComponentType = () => {
	return (
		<ActionBarPrimitive.Root className={uiClassTokens.threadUserActionBar}>
			<ActionBarPrimitive.Copy asChild>
				<TooltipIconButton
					tooltip={THREAD_UI_TEXT.TOOLTIP_COPY}
					className={uiClassTokens.threadUserActionCopy}
				>
					<AuiIf condition={(s) => s.message.isCopied}>
						<CheckIcon className={THREAD_UI_CLASS.COPY_ICON} />
					</AuiIf>
					<AuiIf condition={(s) => !s.message.isCopied}>
						<CopyIcon className={THREAD_UI_CLASS.COPY_ICON} />
					</AuiIf>
				</TooltipIconButton>
			</ActionBarPrimitive.Copy>
			<ActionBarPrimitive.Edit asChild>
				<TooltipIconButton
					tooltip={THREAD_UI_TEXT.TOOLTIP_EDIT}
					className={uiClassTokens.threadUserActionEdit}
				>
					<PencilIcon className={THREAD_UI_CLASS.COPY_ICON} />
				</TooltipIconButton>
			</ActionBarPrimitive.Edit>
		</ActionBarPrimitive.Root>
	);
};

export const UserMessage: ComponentType = () => {
	return (
		<MessagePrimitive.Root
			data-slot="aui_user-message-root"
			className={uiClassTokens.threadUserMessageRoot}
			data-role="user"
		>
			<UserMessageAttachments />

			<div className={uiClassTokens.threadUserMessageContentWrapper}>
				<div className={uiClassTokens.threadUserMessageContent}>
					<MessagePrimitive.Parts components={{ Text: DirectiveText }} />
				</div>
			</div>

			<div className={uiClassTokens.threadUserMeta}>
				<MessageTime />
				<UserActionBar />
			</div>

			<BranchPicker data-slot="aui_user-branch-picker" className="-me-1 justify-end" />
		</MessagePrimitive.Root>
	);
};

export const EditComposer: ComponentType = () => {
	return (
		<MessagePrimitive.Root
			data-slot="aui_edit-composer-wrapper"
			className={uiClassTokens.threadEditComposerRoot}
		>
			<ComposerPrimitive.Root className={uiClassTokens.threadEditComposerPanel}>
				<ComposerPrimitive.Input
					className={uiClassTokens.threadEditComposerInput}
					autoFocus
				/>
				<div className={uiClassTokens.threadEditComposerFooter}>
					<ComposerPrimitive.Cancel asChild>
						<Button
							variant="ghost"
							size="sm"
							className={THREAD_UI_CLASS.EDIT_TOOLBAR_BUTTON}
						>
							{THREAD_UI_TEXT.EDIT_CANCEL_LABEL}
						</Button>
					</ComposerPrimitive.Cancel>
					<ComposerPrimitive.Send asChild>
						<Button
							size="sm"
							className={THREAD_UI_CLASS.EDIT_TOOLBAR_BUTTON}
						>
							{THREAD_UI_TEXT.EDIT_SAVE_LABEL}
						</Button>
					</ComposerPrimitive.Send>
				</div>
			</ComposerPrimitive.Root>
		</MessagePrimitive.Root>
	);
};

export const AssistantMessageDownloadAction: ComponentType = () => {
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
				<TooltipIconButton tooltip={THREAD_UI_TEXT.TOOLTIP_DOWNLOAD_MARKDOWN}>
					<DownloadIcon />
				</TooltipIconButton>
			</ActionBarPrimitive.ExportMarkdown>
		);
	}

	return (
		<TooltipIconButton
			tooltip={THREAD_UI_TEXT.TOOLTIP_DOWNLOAD_ESTIMATE}
			aria-label={THREAD_UI_TEXT.TOOLTIP_DOWNLOAD_ESTIMATE}
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

export const AssistantMessageShareAction: ComponentType = () => {
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
		const latest = [...state.thread.messages].reverse().find((message) => {
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
				setStatusMessage(THREAD_UI_TEXT.SHARE_MESSAGE_PREPARE);
				const prepared = await prepareEstimateShareFiles(
					estimate.projectId,
					estimate.version,
				);
				setStatusMessage(THREAD_UI_TEXT.SHARE_MESSAGE_OPEN_SHARE);
				const result = await sharePreparedEstimateFiles(prepared, {
					title: estimate.title,
					text: [
						estimate.title,
						estimate.region ? `Регион: ${estimate.region}` : null,
						estimate.total ? `Итого: ${estimate.total}` : null,
						THREAD_UI_TEXT.SHARE_SUCCESS_FALLBACK_COPY_PREFIX,
					]
						.filter((line): line is string => Boolean(line))
						.join("\n"),
				});
				setStatusMessage(shareResultMessage(result));
				if (result.status !== "shared") {
					if (result.status === "unsupported") {
						setVisibleError(THREAD_UI_TEXT.SHARE_BROWSER_FALLBACK_TEXT);
					}
					return;
				}
				setCompleted(true);
				window.setTimeout(() => setCompleted(false), 1_800);
				return;
			}

			if (typeof navigator.share === "function") {
				await navigator.share({
					title: THREAD_UI_TEXT.SHARE_SUCCESS_TOAST_TITLE,
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
						: THREAD_UI_TEXT.SHARE_BROWSER_FALLBACK_TEXT;
				setStatusMessage(message);
				setVisibleError(message);
				return;
			}
			try {
				await navigator.clipboard.writeText(text);
				setCompleted(true);
				window.setTimeout(() => setCompleted(false), 1_800);
			} catch {
				// noop
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
							? THREAD_UI_TEXT.TOOLTIP_SHARE_ESTIMATE_DONE
							: THREAD_UI_TEXT.TOOLTIP_SHARE_TEXT_DONE
						: statusMessage ||
							(estimate
								? THREAD_UI_TEXT.TOOLTIP_SHARE_ESTIMATE
								: THREAD_UI_TEXT.TOOLTIP_SHARE_TEXT)
				}
				aria-label={
					estimate ? THREAD_UI_TEXT.TOOLTIP_SHARE_ESTIMATE : THREAD_UI_TEXT.TOOLTIP_SHARE_TEXT
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
				<span role="alert" className={uiClassTokens.threadShareError}>
					{visibleError}
				</span>
			) : null}
		</span>
	);
};

export const AssistantActionBar: ComponentType = () => {
	return (
		<ActionBarPrimitive.Root
			hideWhenRunning
			autohide="never"
			className={uiClassTokens.threadAssistantActionBar}
		>
			<AuiIf
				condition={(s) =>
					s.message.content.some(
						(part) => part.type === "text" && part.text.trim().length > 0,
					)
				}
			>
				<ActionBarPrimitive.Copy asChild>
					<TooltipIconButton tooltip={THREAD_UI_TEXT.ACTIONBAR_COPY_TOOLTIP}>
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
					tooltip={THREAD_UI_TEXT.TOOLTIP_FEEDBACK_GOOD}
					className={uiClassTokens.threadAssistantFeedbackSubmitted}
				>
					<ThumbsUpIcon />
				</TooltipIconButton>
			</ActionBarPrimitive.FeedbackPositive>
			<ActionBarPrimitive.FeedbackNegative asChild>
				<TooltipIconButton
					tooltip={THREAD_UI_TEXT.TOOLTIP_FEEDBACK_BAD}
					className={uiClassTokens.threadAssistantFeedbackSubmitted}
				>
					<ThumbsDownIcon />
				</TooltipIconButton>
			</ActionBarPrimitive.FeedbackNegative>
			<ActionBarPrimitive.Reload asChild>
				<TooltipIconButton tooltip={THREAD_UI_TEXT.TOOLTIP_RETRY}>
					<RefreshCwIcon />
				</TooltipIconButton>
			</ActionBarPrimitive.Reload>
			<AssistantMessageShareAction />
			<AssistantMessageDownloadAction />
			<MessageTiming side="bottom" />
		</ActionBarPrimitive.Root>
	);
};

export const ThreadMessagePrimitives = {
	MessageTime,
	BranchPicker,
	MessageError,
	UserActionBar,
	UserMessage,
	EditComposer,
	AssistantMessageDownloadAction,
	AssistantMessageShareAction,
	AssistantActionBar,
};
