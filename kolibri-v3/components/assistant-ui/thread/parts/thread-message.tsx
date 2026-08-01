"use client";

import {
	MessagePrimitive,
	useAuiState,
} from "@assistant-ui/react";
import {
	LoaderCircleIcon,
	RefreshCwIcon,
} from "lucide-react";
import { type ComponentType, type ReactNode, useContext, useMemo } from "react";
import {
	ReasoningContent,
	ReasoningRoot,
	ReasoningText,
	ReasoningTrigger,
} from "@/components/assistant-ui/reasoning";
import { KolibriGenerativeUI } from "@/components/assistant-ui/generative-ui-renderer";
import { MarkdownText } from "@/components/assistant-ui/markdown-text";
import { parseNativeKolibriGenerativeUI } from "@/lib/generative-ui";
import {
	ToolGroupContent,
	ToolGroupRoot,
	ToolGroupTrigger,
} from "@/components/assistant-ui/tool-group";
import { cn } from "@/lib/utils";
import { uiClassTokens } from "@/components/ui/class-names";
import {
	ThreadComponentsContext,
	groupAssistantPart,
	isRecord,
	weatherPartFingerprint,
	readShareableEstimate,
} from "../thread-context";
import {
	AssistantActionBar,
	BranchPicker,
	EditComposer,
	MessageError,
	MessageTime,
	UserMessage,
} from "./thread-message-primitives";
import { THREAD_UI_CLASS, THREAD_UI_TEXT } from "../thread-ui-constants";

const INVALID_GENERATIVE_UI_NODE = Object.freeze({
	"$type": "__invalid_kolibri_component__",
});

export const AssistantActionBarWithTools: ComponentType = () => {
	return <AssistantActionBar />;
};

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

const AssistantMessage = () => {
	const {
		ToolFallback: ToolFallbackComponent = () => null,
		ToolGroup,
	} = useContext(ThreadComponentsContext);

	const ACTION_BAR_PT = "pt-1.5";
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

		return hiddenIds as ReadonlySet<string>;
	}, [currentMessageId, messageContent, threadMessages]);

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

	const hasVisibleContent = messageContent.some(
		(part) =>
			part.type !== "tool-call" ||
			part.toolName !== "get_weather" ||
			!hiddenWeatherToolCallIds.has(part.toolCallId),
	);
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
		if (
			part.toolName === "get_weather" &&
			!hiddenWeatherToolCallIds.has(part.toolCallId)
		) {
			return true;
		}
		if (part.toolName !== "present") return false;
		if (isRecord(part.args) && part.args.$type === "EstimateEditor") {
			return isLatestEstimateMessage;
		}
		return true;
	});

	if (!hasVisibleContent || !hasRenderableContent) return null;


	type RenderedPart = {
		type: string;
		status?: {
			type?: string;
		};
		indices?: readonly number[];
		toolName?: string;
		toolCallId?: string;
		args?: unknown;
		spec?: unknown;
		toolUI?: ComponentType;
		[key: string]: unknown;
	};

	const renderGroupedPart = ({
		part: partValue,
		children,
	}: {
		part: unknown;
		children: ReactNode;
	}) => {
		const part = partValue as RenderedPart;
		const statusType = part.status?.type;
		switch (part.type) {
			case "group-chainOfThought":
				return <div className={THREAD_UI_CLASS.GROUP_WRAP}>{children}</div>;
			case "group-tool": {
				if (ToolGroup) return <ToolGroup group={partValue as never}>{children}</ToolGroup>;
				return (
					<ToolGroupRoot variant="ghost">
						<ToolGroupTrigger
							count={part.indices?.length ?? 0}
							active={statusType === "running"}
						/>
						<ToolGroupContent>{children}</ToolGroupContent>
					</ToolGroupRoot>
				);
			}
			case "group-reasoning": {
				const running = statusType === "running";
				return (
					<ReasoningRoot
						data-slot="aui_safe-reasoning-status"
						streaming={running}
						variant="ghost"
						className={uiClassTokens.threadReasoningStatus}
					>
						<ReasoningTrigger
							active={running}
							label={
								running
									? THREAD_UI_TEXT.TOOLTIP_REASONING_ACTIVE
									: THREAD_UI_TEXT.TOOLTIP_REASONING_IDLE
							}
						/>
						<ReasoningContent
							role="status"
							aria-live="polite"
							aria-busy={running}
						>
							<ReasoningText>
								<div className={THREAD_UI_CLASS.REASONING_SPACE}>
									<div className={THREAD_UI_CLASS.REASONING_ICON_CONTAINER}>
										<RefreshCwIcon className={THREAD_UI_CLASS.REASONING_ICON_DONE} />
										<span>{THREAD_UI_TEXT.REASONING_STATUS_REQUEST_ACCEPTED}</span>
									</div>
									<div className={THREAD_UI_CLASS.REASONING_ICON_CONTAINER}>
										{running ? (
											<LoaderCircleIcon
												className={THREAD_UI_CLASS.REASONING_ICON_ACTIVE}
											/>
										) : (
											<RefreshCwIcon className={THREAD_UI_CLASS.REASONING_ICON_DONE} />
										)}
										<span>
											{running
												? THREAD_UI_TEXT.REASONING_STATUS_PREPARING
												: THREAD_UI_TEXT.REASONING_STATUS_COMPLETE}
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
				const parsed = parseNativeKolibriGenerativeUI(
					part.spec as Record<string, unknown>,
				);
				return (
					<KolibriGenerativeUI
						node={parsed.ok ? parsed.value : INVALID_GENERATIVE_UI_NODE}
						status={statusType === "running" ? "streaming" : "done"}
					/>
				);
			}
			case "tool-call": {
				if (
					part.toolName === "get_weather" &&
					part.toolCallId !== undefined &&
					hiddenWeatherToolCallIds.has(part.toolCallId)
				) {
					return null;
				}
					if (part.toolName === "present") {
						return (
							<KolibriGenerativeUI
								node={part.args as Record<string, unknown>}
								status={statusType === "running" ? "streaming" : "done"}
							/>
						);
					}
					if (part.toolUI) return <>{part.toolUI}</>;
					const fallbackProps = {
						type: "tool-call" as const,
						toolCallId: part.toolCallId ?? "",
						toolName: part.toolName ?? "",
						argsText: part.argsText ?? "",
						args: isRecord(part.args) ? part.args : {},
						status:
							statusType === "running"
								? { type: "running" }
								: { type: "complete" },
					};
					return <ToolFallbackComponent {...(fallbackProps as any)} />;
			}
			default:
				return null;
			}
		};

	return (
		<MessagePrimitive.Root
			data-slot="aui_assistant-message-root"
			data-role="assistant"
			className={uiClassTokens.threadAssistantMessageRoot}
		>
			<div
				data-slot="aui_assistant-message-content"
				className={uiClassTokens.threadAssistantMessageContent}
			>
					<MessagePrimitive.GroupedParts groupBy={groupAssistantPart}>
						{renderGroupedPart as never}
					</MessagePrimitive.GroupedParts>
				<MessageError />
			</div>

			{hasActionBarContent ? (
				<div
					data-slot="aui_assistant-message-footer"
					className={cn(uiClassTokens.threadAssistantMessageFooter, ACTION_BAR_HEIGHT)}
				>
					<BranchPicker />
					<AssistantActionBarWithTools />
				</div>
			) : null}
		</MessagePrimitive.Root>
	);
};

	export {
			MessageTime,
			BranchPicker,
			MessageError,
			UserMessage,
			EditComposer,
			AssistantActionBar,
			AssistantMessage,
		};
