"use client";

import {
	MessagePrimitive,
	type ToolCallMessagePartComponent,
	useAuiState,
} from "@assistant-ui/react";
import { createElement, type ComponentProps, type ComponentType, type ReactNode, useContext, useMemo } from "react";
import { KolibriGenerativeUI } from "@/components/assistant-ui/generative-ui-renderer";
import { MarkdownText } from "@/components/assistant-ui/markdown-text";
import { kolibriGenerativeUILibrary } from "@/components/assistant-ui/generative-ui-library";
import { GeneratedImageToolUI } from "@/components/assistant-ui/generated-image-tool";
import {
	DeveloperActivityGroup,
	DeveloperCommandToolUI,
	DeveloperFileChangeToolUI,
} from "@/components/assistant-ui/developer-activity-tool";
import { WeatherToolUI } from "@/components/assistant-ui/product-widgets/weather";
import { EstimateDocumentPackWidget } from "@/components/assistant-ui/product-widgets/estimate-document-pack";
import { ToolApprovalActions, ToolFallback } from "@/components/assistant-ui/tool-fallback";
import { cn } from "@/lib/utils";
import { uiClassTokens } from "@/components/ui/class-names";
import {
	ThreadComponentsContext,
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
import { THREAD_UI_CLASS } from "../thread-ui-constants";

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
		ToolFallback: ToolFallbackComponent = ToolFallback,
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

	const generativeUIComponents = useMemo(
		() =>
			Object.fromEntries(
				Object.entries(kolibriGenerativeUILibrary).map(([name, entry]) => [
					name,
					entry.render,
				]),
			) as Record<string, ComponentType<Record<string, unknown>>>,
		[],
	);
	const weatherRenderer = useMemo<ToolCallMessagePartComponent>(
		() => (props) =>
			props.toolCallId && hiddenWeatherToolCallIds.has(props.toolCallId) ? null : (
				<WeatherToolUI {...(props as ComponentProps<typeof WeatherToolUI>)} />
			),
		[hiddenWeatherToolCallIds],
	);
	const withApproval = useMemo(
		() =>
			(renderer: ToolCallMessagePartComponent): ToolCallMessagePartComponent =>
				(props) => (
					<div className="space-y-2">
						{createElement(renderer, props)}
						<ToolApprovalActions {...props} />
					</div>
				),
		[],
	);
	const presentRenderer = useMemo<ToolCallMessagePartComponent>(
		() => (props) => {
			if (
				isRecord(props.args) &&
				props.args.$type === "EstimateEditor" &&
				!isLatestEstimateMessage
			) {
				return null;
			}
			return (
				<KolibriGenerativeUI
					node={props.args}
					status={props.status.type === "running" ? "streaming" : "done"}
				/>
			);
		},
		[isLatestEstimateMessage],
	);
	const documentPackRenderer = useMemo<ToolCallMessagePartComponent>(
		() => (props) => {
			if (!isRecord(props.args)) return null;
			return (
				<EstimateDocumentPackWidget
					{...(props.args as ComponentProps<typeof EstimateDocumentPackWidget>)}
				/>
			);
		},
		[],
	);
	const partsComponents = useMemo(
		() => ({
			Text: MarkdownText,
			Reasoning: () => null,
			generativeUI: {
				components: generativeUIComponents,
				Fallback: () => null,
			},
			tools: {
				by_name: {
					generate_image: withApproval(GeneratedImageToolUI),
					get_weather: withApproval(weatherRenderer),
					developer_command: withApproval(DeveloperCommandToolUI),
					developer_file_change: withApproval(DeveloperFileChangeToolUI),
					create_estimate_document_pack: documentPackRenderer,
					present: withApproval(presentRenderer),
				},
				Fallback: ToolFallbackComponent,
			},
			ToolGroup: DeveloperActivityGroup,
			ReasoningGroup: ({ children }: { children?: ReactNode }) => (
				<details
					className={uiClassTokens.threadReasoningStatus}
					data-slot="aui_safe-reasoning-status"
				>
					<summary className="cursor-pointer select-none" aria-label="Показать ход выполнения">
						Ход выполнения
					</summary>
					<div role="status" aria-live="polite">{children}</div>
				</details>
			),
		}),
		[generativeUIComponents, presentRenderer, weatherRenderer, documentPackRenderer, ToolFallbackComponent, withApproval],
	);

	if (!hasVisibleContent || !hasRenderableContent) return null;

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
					<MessagePrimitive.Parts components={partsComponents} />
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
