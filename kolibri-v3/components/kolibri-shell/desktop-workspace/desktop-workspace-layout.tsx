"use client";

import type { ReactNode } from "react";
import {
	ResizableHandle,
	ResizablePanel,
	ResizablePanelGroup,
} from "@/components/ui/resizable";
import { cn } from "@/lib/utils";

export type DesktopWorkspaceLayoutProps = {
	auxiliary: ReactNode;
	auxiliaryFullscreen: boolean;
	auxiliaryOpen: boolean;
	chat: ReactNode;
	chrome: ReactNode;
	composer: ReactNode;
	header: ReactNode;
	navigation: ReactNode;
	navigationOpen: boolean;
	primary: ReactNode;
	primaryOpen: boolean;
};

export function DesktopWorkspaceLayout({
	auxiliary,
	auxiliaryFullscreen,
	auxiliaryOpen,
	chat,
	chrome,
	composer,
	header,
	navigation,
	navigationOpen,
	primary,
	primaryOpen,
}: DesktopWorkspaceLayoutProps) {
	const chatHidden = primaryOpen;

	return (
		<div
			data-slot="kolibri-workspace-shell"
			data-workspace-mode="desktop"
			className="bg-background text-foreground relative flex h-dvh max-h-dvh min-w-0 flex-col overflow-hidden"
		>
			<ResizablePanelGroup
				orientation="horizontal"
				className="min-h-0 min-w-0 flex-1"
			>
		{navigationOpen && !auxiliaryFullscreen ? (
						<>
							<ResizablePanel
								id="project-navigation"
								defaultSize={320}
								minSize={280}
								maxSize={360}
								groupResizeBehavior="preserve-pixel-size"
								className="min-h-0 min-w-0 overflow-hidden"
							>
							<div id="workspace-project-navigation" className="h-full">
								{navigation}
							</div>
						</ResizablePanel>
						<ResizableHandle aria-label="Изменить ширину навигации" />
					</>
				) : null}

				<ResizablePanel
					id="primary-workspace"
					// When navigation is docked the chat canvas keeps a 640 px floor
					// so it never gets squeezed; once navigation switches to the
					// overlay (narrow window) the canvas is the only panel and must
					// be free to shrink down to the viewport width.
					minSize={navigationOpen ? 640 : 0}
					className="min-h-0 min-w-0 overflow-hidden"
				>
					<main className="flex h-full min-h-0 min-w-0 flex-col overflow-hidden">
						{header}
						<div className="relative min-h-0 min-w-0 flex-1 overflow-hidden">
							<section
								aria-label="Диалог с Kolibri"
								aria-hidden={chatHidden ? true : undefined}
								inert={chatHidden ? true : undefined}
								className={cn(
									"absolute inset-0 min-h-0 min-w-0 overflow-hidden",
									chatHidden && "invisible pointer-events-none",
								)}
							>
								{chat}
							</section>
							{primaryOpen ? (
								<section
									data-slot="primary-product-surface"
									className="absolute inset-0 min-h-0 min-w-0 overflow-hidden"
								>
									{primary}
								</section>
							) : null}
						</div>
						{composer}
					</main>
				</ResizablePanel>

				{auxiliaryOpen && !auxiliaryFullscreen ? (
					<>
						<ResizableHandle aria-label="Изменить ширину дополнительного канваса" />
						<ResizablePanel
								id="auxiliary-canvas"
								defaultSize={400}
								minSize={320}
								maxSize={640}
								groupResizeBehavior="preserve-pixel-size"
								className="min-h-0 min-w-0 overflow-hidden"
							>
							{auxiliary}
						</ResizablePanel>
					</>
				) : null}
			</ResizablePanelGroup>

			{auxiliaryFullscreen ? auxiliary : null}
			{chrome}
		</div>
	);
}
