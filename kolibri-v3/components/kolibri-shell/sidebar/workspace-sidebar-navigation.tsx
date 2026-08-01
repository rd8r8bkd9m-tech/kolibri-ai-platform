"use client";

import { ThreadListPrimitive } from "@assistant-ui/react";
import { SquarePen } from "lucide-react";
import { ThreadListItems } from "@/components/assistant-ui/thread-list";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { shouldCloseThreadDrawerForClick } from "@/lib/mobile-thread-navigation";
import type { WorkspaceSidebarProps } from "./constants";
import {
	WorkspaceSidebarBody,
	WorkspaceSidebarSectionHeading,
} from "@/components/ui/shared-wrappers";
import { uiClassTokens } from "@/components/ui/class-names";
import {
	NAVIGATION_ITEMS,
	type WorkspaceSidebarDestination,
} from "./constants";
import { SidebarDestination } from "./sidebar-controls";

type WorkspaceSidebarNavigationProps = Pick<
	WorkspaceSidebarProps,
	| "activeDestination"
	| "isOverlay"
	| "closeOnThreadSelect"
	| "onOpenChat"
	| "onOpenDocuments"
	| "onOpenProjects"
	| "onOpenReferenceCatalog"
	| "onRequestClose"
>;

const sidebarDestinationHandlers: Record<
	WorkspaceSidebarDestination,
	(payload: {
		onOpenDocuments?: WorkspaceSidebarProps["onOpenDocuments"];
		onOpenProjects?: WorkspaceSidebarProps["onOpenProjects"];
		onOpenReferenceCatalog?: WorkspaceSidebarProps["onOpenReferenceCatalog"];
	}) => void
> = {
	projects: ({ onOpenProjects }) => onOpenProjects?.(),
	documents: ({ onOpenDocuments }) => onOpenDocuments?.(),
	references: ({ onOpenReferenceCatalog }) => onOpenReferenceCatalog?.(),
};

export function WorkspaceSidebarNavigation({
	activeDestination = "chat",
	isOverlay = false,
	closeOnThreadSelect = true,
	onOpenChat,
	onOpenDocuments,
	onOpenProjects,
	onOpenReferenceCatalog,
	onRequestClose,
}: WorkspaceSidebarNavigationProps) {
	return (
		<WorkspaceSidebarBody data-slot="workspace-sidebar-body">
			<nav aria-label="Основные разделы">
				<ul className="space-y-0.5">
					<li>
						<ThreadListPrimitive.New asChild>
							<Button
								type="button"
								variant="ghost"
								onClick={onOpenChat}
								data-slot="workspace-sidebar-destination"
								className={cn(
									uiClassTokens.sidebarDestinationButton,
									"text-muted-foreground",
								)}
							>
								<SquarePen className="size-[17px]" />
								<span>Новая задача</span>
							</Button>
						</ThreadListPrimitive.New>
					</li>
					{NAVIGATION_ITEMS.map((item) => (
						<SidebarDestination
							key={item.id}
							{...item}
							active={activeDestination === item.id}
							onClick={() =>
								sidebarDestinationHandlers[item.id]({
									onOpenDocuments,
									onOpenProjects,
									onOpenReferenceCatalog,
								})
							}
						/>
					))}
				</ul>
			</nav>

			<section className="mt-5" aria-labelledby="recent-chats-heading">
				<WorkspaceSidebarSectionHeading id="recent-chats-heading">
					Диалоги
				</WorkspaceSidebarSectionHeading>
				<nav
					aria-label="Диалоги пользователя"
					className="pl-0.5"
					onClickCapture={(event) => {
						if (!isOverlay || !closeOnThreadSelect) return;
						const trigger =
							event.target instanceof Element
								? event.target.closest(
									'[data-slot="aui_thread-list-item-trigger"]',
								)
							: null;
						if (
							shouldCloseThreadDrawerForClick({
								isThreadTrigger: trigger !== null,
								longPressConsumed:
									trigger?.getAttribute(
										"data-thread-long-press-consumed",
									) === "true",
							})
						) {
							onRequestClose?.();
						}
					}}
				>
					<ThreadListItems />
				</nav>
			</section>
		</WorkspaceSidebarBody>
	);
}
