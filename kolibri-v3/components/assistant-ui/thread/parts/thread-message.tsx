"use client";

import {
	MessagePrimitive,
	type ReasoningMessagePartComponent,
	type ToolCallMessagePartComponent,
	useAuiState,
	useMessageTiming,
} from "@assistant-ui/react";
import {
	BrainIcon,
	CheckCircle2Icon,
	ChevronDownIcon,
	LoaderCircleIcon,
} from "lucide-react";
import {
	createElement,
	type ComponentProps,
	type ComponentType,
	type ReactNode,
	useContext,
	useMemo,
} from "react";
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

const formatWorkDuration = (milliseconds: number): string => {
	const seconds = Math.max(1, Math.round(milliseconds / 1_000));
	const minutes = Math.floor(seconds / 60);
	const remainder = seconds % 60;
	if (minutes === 0) return `${seconds}с`;
	return remainder === 0 ? `${minutes}м` : `${minutes}м ${remainder}с`;
};

export const AssistantActionBarWithTools: ComponentType = () => {
	return <AssistantActionBar />;
};

const ReasoningBlock: ReasoningMessagePartComponent = ({ text }) => {
	const content = text?.trim();
	const isStreaming = useAuiState((state) => state.thread.isRunning);
	const timing = useMessageTiming();

	if (!content) return null;

	const duration =
		timing?.totalStreamTime === undefined
			? ""
			: ` · ${formatWorkDuration(timing.totalStreamTime)}`;

	return (
		<details
			className="border-border/70 bg-muted/20 group/reasoning-step rounded-lg border"
			data-slot="reasoning-step"
			open={isStreaming || undefined}
		>
			<summary className="hover:bg-muted/35 flex min-h-9 cursor-pointer list-none items-center gap-2 rounded-lg px-2.5 py-1.5 text-xs font-medium transition-colors [&::-webkit-details-marker]:hidden">
				{isStreaming ? (
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
				<BrainIcon className="size-3.5 shrink-0" aria-hidden="true" />
				<span className="shrink-0">
					{isStreaming ? "Обдумываю задачу…" : "Обдумал задачу"}
					{duration}
				</span>
				<span className="text-muted-foreground ml-auto truncate text-[10px] font-normal">
					Подробности рассуждения
				</span>
				<ChevronDownIcon
					className="size-3.5 shrink-0 transition-transform group-open/reasoning-step:rotate-180"
					aria-hidden="true"
				/>
			</summary>
			<div className="border-border/60 border-t px-2.5 py-2">
				<div className="text-muted-foreground max-h-64 overflow-y-auto text-[12px] leading-relaxed whitespace-pre-wrap">
					{content}
				</div>
			</div>
		</details>
	);
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
			Reasoning: ReasoningBlock,
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
			ReasoningGroup: ({ children }: { children?: ReactNode }) => {
				const running = useAuiState((state) => state.thread.isRunning);
				const timing = useMessageTiming();
				const durationLabel =
					timing?.totalStreamTime === undefined
						? ""
						: ` ${formatWorkDuration(timing.totalStreamTime)}`;
				return (
					<details
						className="group/work-feed min-w-0 max-w-full"
						open={running || undefined}
						data-slot="work-feed"
					>
						<summary className="text-muted-foreground hover:text-foreground flex cursor-pointer list-none items-center gap-2 py-1 text-sm transition-colors [&::-webkit-details-marker]:hidden">
							<BrainIcon className="size-4 shrink-0" aria-hidden="true" />
							<span>Ход работы{durationLabel}</span>
							<ChevronDownIcon
								className="size-4 shrink-0 transition-transform group-open/work-feed:rotate-180"
								aria-hidden="true"
							/>
						</summary>
						<div
							className="space-y-1.5 pt-1.5"
							role="log"
							aria-label="Ход работы агента"
						>
							{children}
						</div>
					</details>
				);
			},
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
