"use client";

import { AuiIf, ThreadPrimitive, useAuiState } from "@assistant-ui/react";
import { type FC, useContext } from "react";

import { ThreadFollowupSuggestions } from "@/components/assistant-ui/follow-up-suggestions";
import {
	Composer,
	ThreadMessage,
	ThreadScrollToBottom,
	RunProgressPill,
	ThreadSuggestions,
	ThreadWelcome,
} from "../thread-parts";
import {
	isNewChatView,
	ThreadCompactContext,
	ThreadComponentsContext,
} from "../thread-context";
import { uiClassTokens } from "@/components/ui/class-names";
import { ThreadViewportContent } from "@/components/ui/shared-wrappers";
import { THREAD_ROOT_CSS_VARS } from "../thread-layout-config";
import { ThreadShell } from "../thread-shell";

export const ThreadViewportScreen: FC = () => {
	const { Welcome = ThreadWelcome } = useContext(ThreadComponentsContext);
	const compact = useContext(ThreadCompactContext);
	const isRunning = useAuiState((s) => s.thread.isRunning);

	return (
		<ThreadShell
			compact={compact}
			isRunning={isRunning}
			className={uiClassTokens.threadRoot}
			style={THREAD_ROOT_CSS_VARS}
		>
			<ThreadPrimitive.Viewport
				turnAnchor="top"
				autoScroll
				scrollToBottomOnInitialize
				scrollToBottomOnRunStart
				scrollToBottomOnThreadSwitch
				data-slot="aui_thread-viewport"
				className={uiClassTokens.threadViewport}
			>
				<ThreadViewportContent>
					<AuiIf condition={isNewChatView}>
						<div
							data-slot="aui_empty-state"
							className={uiClassTokens.threadEmptyState}
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
						className={uiClassTokens.threadMessageGroup}
					>
						<ThreadPrimitive.Messages>{() => <ThreadMessage />}</ThreadPrimitive.Messages>
					</div>

					<ThreadPrimitive.ViewportFooter
						data-composer-placement="bottom"
						className={uiClassTokens.threadViewportFooter}
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
				</ThreadViewportContent>
			</ThreadPrimitive.Viewport>
		</ThreadShell>
	);
};
