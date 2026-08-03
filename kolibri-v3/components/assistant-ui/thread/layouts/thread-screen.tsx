"use client";

import {
	AuiIf,
	SelectionToolbarPrimitive,
	ThreadPrimitive,
	useAuiState,
} from "@assistant-ui/react";
import { type FC, useContext } from "react";

import { AgUiInterruptSurface } from "@/components/assistant-ui/ag-ui-controls";
import { EstimateGenerationStatus } from "@/components/assistant-ui/product-widgets/estimate-generation-status";
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

export const ThreadViewportScreen: FC<{ showComposer?: boolean }> = ({
	showComposer = true,
}) => {
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
					<AgUiInterruptSurface />
					<SelectionToolbarPrimitive.Root className="border-border bg-popover text-popover-foreground fixed z-50 flex items-center gap-1 rounded-lg border p-1 shadow-lg">
						<SelectionToolbarPrimitive.Quote className="rounded-md px-2 py-1 text-xs font-medium hover:bg-muted focus-visible:outline-none focus-visible:ring-2">
							Цитировать
						</SelectionToolbarPrimitive.Quote>
					</SelectionToolbarPrimitive.Root>
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
						<ThreadPrimitive.Messages>
							{() => <ThreadMessage />}
						</ThreadPrimitive.Messages>
					</div>

					<ThreadPrimitive.ViewportFooter
						data-composer-placement="bottom"
						className={uiClassTokens.threadViewportFooter}
					>
						<ThreadScrollToBottom />
						<ThreadFollowupSuggestions />
						<EstimateGenerationStatus />
						<AuiIf condition={(s) => s.thread.isRunning}>
							<RunProgressPill />
						</AuiIf>
						<AuiIf condition={(s) => isNewChatView(s) && s.composer.isEmpty}>
							<ThreadSuggestions />
						</AuiIf>
						{showComposer ? <Composer /> : null}
					</ThreadPrimitive.ViewportFooter>
				</ThreadViewportContent>
			</ThreadPrimitive.Viewport>
		</ThreadShell>
	);
};
