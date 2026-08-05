"use client";

import { PanelRight, SquareMinus } from "lucide-react";
import type { FC } from "react";

import { Thread } from "@/components/assistant-ui/thread";
import { cn } from "@/lib/utils";

export const CodexMain: FC<{
	onOpenAccount?: () => void;
	onOpenContextPanel?: () => void;
	contextOpen?: boolean;
}> = ({ onOpenAccount, onOpenContextPanel, contextOpen = false }) => {
	return (
		<main className="relative flex h-full min-w-0 flex-1 flex-col bg-(--color-surface)">
			<div className="flex h-[46px] shrink-0 items-center justify-end gap-1 px-3">
				<button
					type="button"
					className="rounded-md p-1.5 text-(--color-icon-secondary) hover:bg-black/[.05]"
				>
					<SquareMinus className="size-4" />
				</button>
				<button
					type="button"
					onClick={onOpenContextPanel}
					aria-pressed={contextOpen}
					className={cn(
						"rounded-md p-1.5 text-(--color-icon-secondary) hover:bg-black/[.05]",
						contextOpen && "bg-black/[.07] text-(--color-text-foreground)",
					)}
				>
					<PanelRight className="size-4" />
				</button>
			</div>
			<div className="min-h-0 flex-1">
				<Thread
					onOpenAccount={onOpenAccount}
					onOpenContextPanel={onOpenContextPanel}
					workspaceOpen={contextOpen}
				/>
			</div>
		</main>
	);
};
