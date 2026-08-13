"use client";

import {
	ThreadListItemMorePrimitive,
	ThreadListItemPrimitive,
	useAui,
	useAuiState,
} from "@assistant-ui/react";
import {
	ArchiveIcon,
	ArchiveRestoreIcon,
	Clock3Icon,
	FolderKanbanIcon,
	MoreHorizontalIcon,
	PinIcon,
	PinOffIcon,
	Trash2Icon,
} from "lucide-react";
import {
	type FC,
	useEffect,
	useRef,
	useState,
	useSyncExternalStore,
} from "react";
import {
	canStartThreadLongPress,
	compactThreadMenuSnapshot,
	serverCompactThreadMenuSnapshot,
	shouldIgnoreThreadMenuCloseRequest,
	subscribeCompactThreadMenu,
	THREAD_LONG_PRESS_CLICK_SUPPRESSION_MS,
	THREAD_LONG_PRESS_DURATION_MS,
	THREAD_LONG_PRESS_MOVE_TOLERANCE_PX,
} from "@/components/assistant-ui/thread-list/thread-list-utils";
import { Button } from "@/components/ui/button";
import {
	HoverCard,
	HoverCardContent,
	HoverCardTrigger,
} from "@/components/ui/hover-card";
import { cn } from "@/lib/utils";
import { uiClassTokens } from "@/components/ui/class-names";
import { ThreadListItemMetaCard } from "@/components/ui/shared-wrappers";

export const ThreadListItem: FC = () => {
	const aui = useAui();
	const [menuOpen, setMenuOpen] = useState(false);
	const [longPressing, setLongPressing] = useState(false);
	const compactThreadMenu = useSyncExternalStore(
		subscribeCompactThreadMenu,
		compactThreadMenuSnapshot,
		serverCompactThreadMenuSnapshot,
	);
	const longPressRef = useRef<{
		timer: ReturnType<typeof setTimeout>;
		x: number;
		y: number;
	} | null>(null);
	const threadTriggerRef = useRef<HTMLButtonElement | null>(null);
	const suppressNextClickRef = useRef(false);
	const suppressClickResetTimerRef = useRef<ReturnType<
		typeof setTimeout
	> | null>(null);
	const title = useAuiState(
		(state) => state.threadListItem.title || "Новый диалог",
	);
	const status = useAuiState((state) => state.threadListItem.status);
	const lastMessageAt = useAuiState(
		(state) => state.threadListItem.lastMessageAt,
	);
	const custom = useAuiState((state) => state.threadListItem.custom);
	const isPinned = custom?.pinned === true;
	const isDraft = custom?.draft === true;
	const projectId =
		typeof custom?.projectId === "string" ? custom.projectId : null;
	const lastActivity = lastMessageAt
		? new Intl.DateTimeFormat("ru-RU", {
				dateStyle: "medium",
				timeStyle: "short",
			}).format(lastMessageAt)
		: "Сообщений пока нет";

	const cancelLongPress = () => {
		setLongPressing(false);
		if (longPressRef.current) {
			clearTimeout(longPressRef.current.timer);
			longPressRef.current = null;
		}
	};

	const clearConsumedLongPress = () => {
		suppressNextClickRef.current = false;
		if (suppressClickResetTimerRef.current) {
			clearTimeout(suppressClickResetTimerRef.current);
			suppressClickResetTimerRef.current = null;
		}
		threadTriggerRef.current?.removeAttribute(
			"data-thread-long-press-consumed",
		);
	};

	const handleMenuOpenChange = (open: boolean) => {
		if (
			shouldIgnoreThreadMenuCloseRequest({
				open,
				longPressClickPending: suppressNextClickRef.current,
			})
		) {
			return;
		}
		setMenuOpen(open);
		if (!open) clearConsumedLongPress();
	};

	const consumeLongPressClick = (event: {
		preventDefault: () => void;
		stopPropagation: () => void;
	}) => {
		if (!suppressNextClickRef.current) return;
		event.preventDefault();
		event.stopPropagation();
		clearConsumedLongPress();
	};

	const preventConsumedLongPressNavigation = (event: {
		preventDefault: () => void;
	}) => {
		if (suppressNextClickRef.current) event.preventDefault();
	};

	useEffect(
		() => () => {
			if (longPressRef.current) {
				clearTimeout(longPressRef.current.timer);
			}
			if (suppressClickResetTimerRef.current) {
				clearTimeout(suppressClickResetTimerRef.current);
			}
			threadTriggerRef.current?.removeAttribute(
				"data-thread-long-press-consumed",
			);
		},
		[],
	);

	const threadMenuItemClass = cn(
		uiClassTokens.threadListMenuItem,
		compactThreadMenu && "min-h-12 rounded-xl px-3 text-[16px]",
	);

	return (
		<ThreadListItemPrimitive.Root
			data-slot="aui_thread-list-item"
			data-long-pressing={longPressing ? "true" : undefined}
			data-thread-action-menu-open={menuOpen ? "true" : undefined}
			className={uiClassTokens.threadListItem}
		>
			<HoverCard>
				<HoverCardTrigger asChild>
					<ThreadListItemPrimitive.Trigger
						ref={threadTriggerRef}
						data-slot="aui_thread-list-item-trigger"
						className={uiClassTokens.threadListItemTrigger}
						aria-label={`Открыть задачу «${title}»`}
						onPointerDown={(event) => {
							if (
								!canStartThreadLongPress({
									isDraft,
									pointerType: event.pointerType,
								})
							) {
								return;
							}
							cancelLongPress();
							setLongPressing(true);
							const trigger = event.currentTarget;
							longPressRef.current = {
								x: event.clientX,
								y: event.clientY,
								timer: setTimeout(() => {
									setLongPressing(false);
									suppressNextClickRef.current = true;
									trigger.setAttribute(
										"data-thread-long-press-consumed",
										"true",
									);
									suppressClickResetTimerRef.current = setTimeout(
										clearConsumedLongPress,
										THREAD_LONG_PRESS_CLICK_SUPPRESSION_MS,
									);
									longPressRef.current = null;
									globalThis.navigator.vibrate?.(10);
									setMenuOpen(true);
								}, THREAD_LONG_PRESS_DURATION_MS),
							};
						}}
						onPointerMove={(event) => {
							const pending = longPressRef.current;
							if (
								pending &&
								Math.hypot(
									event.clientX - pending.x,
									event.clientY - pending.y,
								) > THREAD_LONG_PRESS_MOVE_TOLERANCE_PX
							) {
								cancelLongPress();
							}
						}}
						onPointerUp={cancelLongPress}
						onPointerCancel={cancelLongPress}
						onPointerLeave={cancelLongPress}
						onContextMenu={(event) => {
							if (isDraft) {
								event.preventDefault();
								return;
							}
							event.preventDefault();
							cancelLongPress();
							setMenuOpen(true);
						}}
						onClickCapture={preventConsumedLongPressNavigation}
						onClick={consumeLongPressClick}
					>
						<span
							data-slot="aui_thread-list-item-title"
							className="min-w-0 flex-1 truncate"
						>
							<ThreadListItemPrimitive.Title fallback="Новый диалог" />
						</span>
					</ThreadListItemPrimitive.Trigger>
				</HoverCardTrigger>
				<HoverCardContent className={uiClassTokens.threadListItemHoverCardContent}>
					<div className="flex items-start gap-2.5">
						<span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground">
							<FolderKanbanIcon className="size-4" />
						</span>
						<div className="min-w-0 flex-1">
							<div className="flex items-center gap-1.5">
								<p className="line-clamp-2 text-sm leading-5 font-medium">
									{title}
								</p>
								{isPinned ? (
									<PinIcon className="size-3.5 shrink-0 text-muted-foreground" />
								) : null}
							</div>
							<p className="text-muted-foreground mt-0.5 text-xs">
								{status === "archived" ? "Диалог в архиве" : "Диалог проекта"}
							</p>
						</div>
					</div>
					<ThreadListItemMetaCard>
						<div className={uiClassTokens.threadListItemMetaRow}>
							<Clock3Icon className="mt-0.5 size-3.5 shrink-0" />
							<span>{lastActivity}</span>
						</div>
						{projectId ? (
							<div className={uiClassTokens.threadListItemMetaRow}>
								<FolderKanbanIcon className="mt-0.5 size-3.5 shrink-0" />
								<span className="min-w-0 break-all">Проект · {projectId}</span>
							</div>
						) : null}
					</ThreadListItemMetaCard>
					<Button
						type="button"
						size="sm"
						variant="secondary"
						className={uiClassTokens.threadListItemActionButton}
						onClick={() => {
							if (status === "archived") {
								aui.threadListItem.unarchive();
								return;
							}
							aui.threadListItem.switchTo();
						}}
					>
						{status === "archived" ? "Вернуть из архива" : "Открыть диалог"}
					</Button>
				</HoverCardContent>
			</HoverCard>

			{!isDraft ? (
				<ThreadListItemMorePrimitive.Root
					sharedFocusGroup
					open={menuOpen}
					onOpenChange={handleMenuOpenChange}
				>
					<ThreadListItemMorePrimitive.Trigger
						aria-label={`Действия с диалогом «${title}»`}
						render={
							<button
								type="button"
								className={cn(uiClassTokens.threadListMenuTrigger)}
							/>
						}
					>
						<MoreHorizontalIcon className="size-4" />
					</ThreadListItemMorePrimitive.Trigger>
					<ThreadListItemMorePrimitive.Content
						align={compactThreadMenu ? "center" : "start"}
						side={compactThreadMenu ? "bottom" : "right"}
						sideOffset={compactThreadMenu ? 10 : 6}
						collisionPadding={8}
						className={cn(
							uiClassTokens.threadListMenuContent,
							compactThreadMenu &&
								uiClassTokens.threadListMenuCompactContent,
						)}
					>
						<ThreadListItemMorePrimitive.Item
							className={threadMenuItemClass}
							onSelect={() =>
								aui.threadListItem.updateCustom({
									...custom,
									pinned: !isPinned,
								})
							}
						>
							{isPinned ? (
								<PinOffIcon className="size-4" />
							) : (
								<PinIcon className="size-4" />
							)}
							{isPinned ? "Открепить" : "Закрепить"}
						</ThreadListItemMorePrimitive.Item>
						<ThreadListItemMorePrimitive.Item
							className={threadMenuItemClass}
							onSelect={() => {
								if (status === "archived") {
									aui.threadListItem.unarchive();
								} else {
									aui.threadListItem.archive();
								}
							}}
						>
							{status === "archived" ? (
								<ArchiveRestoreIcon className="size-4" />
							) : (
								<ArchiveIcon className="size-4" />
							)}
							{status === "archived" ? "Вернуть из архива" : "Архивировать"}
						</ThreadListItemMorePrimitive.Item>
						<ThreadListItemMorePrimitive.Separator className="my-1 h-px bg-border" />
						<ThreadListItemMorePrimitive.Item
							className={cn(
								threadMenuItemClass,
								"text-destructive data-[highlighted]:bg-destructive/10",
							)}
							onSelect={() => {
								const confirmed = globalThis.confirm(
									`Удалить диалог «${title}» из списка? Проект и документы сохранятся.`,
								);
								if (confirmed) aui.threadListItem.delete();
							}}
						>
							<Trash2Icon className="size-4" />
							Удалить диалог
						</ThreadListItemMorePrimitive.Item>
					</ThreadListItemMorePrimitive.Content>
				</ThreadListItemMorePrimitive.Root>
			) : null}
		</ThreadListItemPrimitive.Root>
	);
};
