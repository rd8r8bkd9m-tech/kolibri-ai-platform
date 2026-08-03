"use client";

import {
	Maximize2,
	Minimize2,
	Minus,
	PanelRight,
	type LucideIcon,
} from "lucide-react";
import { type ReactNode, useId } from "react";
import { Button } from "@/components/ui/button";
import {
	Tooltip,
	TooltipContent,
	TooltipProvider,
	TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

export type CanvasFramePlacement = "bottom" | "primary" | "right";

export type CanvasFrameTab = {
	id: string;
	title: string;
};

export type CanvasFrameHeaderTab = {
	icon?: LucideIcon;
	id: string;
	title: string;
};

export type CanvasFrameProps = {
	activeTabId?: string;
	children: ReactNode;
	className?: string;
	compactChrome?: boolean;
	activeHeaderTabId?: string;
	headerActions?: ReactNode;
	headerTabs?: readonly CanvasFrameHeaderTab[];
	label: string;
	maximized?: boolean;
	onClose?: () => void;
	onHeaderTabSelect?: (tabId: string) => void;
	onMinimize?: () => void;
	onPlacementChange?: (placement: CanvasFramePlacement) => void;
	onTabSelect?: (tabId: string) => void;
	onToggleMaximize?: () => void;
	placement?: CanvasFramePlacement;
	tabs?: readonly CanvasFrameTab[];
};

export function CanvasFrame({
	activeTabId,
	children,
	className,
	compactChrome = false,
	activeHeaderTabId,
	headerActions,
	headerTabs = [],
	label,
	maximized = false,
	onClose,
	onHeaderTabSelect,
	onMinimize,
	onPlacementChange,
	onTabSelect,
	onToggleMaximize,
	placement = "right",
	tabs = [],
}: CanvasFrameProps) {
	const domPrefix = useId().replace(/:/g, "");
	const selectedIndex = Math.max(
		0,
		tabs.findIndex((tab) => tab.id === activeTabId),
	);

	return (
		<TooltipProvider delayDuration={300}>
			<section
				data-slot="canvas-frame"
				data-canvas-fullscreen={maximized}
				data-canvas-placement={placement}
				className={cn(
					"border-border bg-background @container flex h-full min-h-0 min-w-0 flex-col overflow-hidden",
					maximized || compactChrome ? "border-l-0" : "border-l",
					className,
				)}
				aria-label={label}
			>
				{compactChrome ? null : (
					<>
						<header className="border-border/80 bg-background flex h-12 shrink-0 items-center gap-2 border-b px-3">
							{tabs.length > 0 ? (
								<CanvasTabList
									activeTabId={activeTabId}
									domPrefix={domPrefix}
									onTabSelect={onTabSelect}
									tabs={tabs}
								/>
							) : headerTabs.length > 0 ? (
								<CanvasHeaderTabList
									activeTabId={activeHeaderTabId}
									onTabSelect={onHeaderTabSelect}
									tabs={headerTabs}
								/>
							) : (
								<span className="min-w-0 flex-1" aria-hidden="true" />
							)}
							<div className="ml-auto flex shrink-0 items-center gap-1">
								{headerActions}
								{onToggleMaximize ? (
									<CanvasIconAction
										data-slot="canvas-fullscreen-toggle"
										label={maximized ? "Вернуть в панель" : "На весь экран"}
										aria-pressed={maximized}
										onClick={onToggleMaximize}
									>
										{maximized ? (
											<Minimize2 className="size-4" aria-hidden="true" />
										) : (
											<Maximize2 className="size-4" aria-hidden="true" />
										)}
									</CanvasIconAction>
								) : null}
								{onMinimize ? (
									<CanvasIconAction
										data-slot="canvas-minimize"
										label="Свернуть рабочую область"
										onClick={onMinimize}
									>
										<Minus className="size-4" aria-hidden="true" />
									</CanvasIconAction>
								) : null}
								{!maximized && onPlacementChange && placement !== "right" ? (
									<CanvasIconAction
										label="Закрепить справа"
										onClick={() => onPlacementChange("right")}
									>
										<PanelRight className="size-4" aria-hidden="true" />
									</CanvasIconAction>
								) : null}
								{onClose ? (
									<CanvasIconAction
										label="Закрыть рабочую область"
										onClick={onClose}
									>
										<PanelRight className="size-4" aria-hidden="true" />
									</CanvasIconAction>
								) : null}
							</div>
						</header>
						{tabs.length > 0 && headerTabs.length > 0 ? (
							<div className="border-border/80 bg-background flex h-9 shrink-0 items-center border-b px-3">
								<CanvasHeaderTabList
									activeTabId={activeHeaderTabId}
									onTabSelect={onHeaderTabSelect}
									tabs={headerTabs}
								/>
							</div>
						) : null}
					</>
				)}
				<div
					id={`${domPrefix}-tabpanel`}
					role="tabpanel"
					aria-labelledby={
						tabs.length > 0 && activeTabId
							? `${domPrefix}-tab-${selectedIndex}`
							: undefined
					}
					className="flex min-h-0 flex-1 flex-col"
				>
					{children}
				</div>
			</section>
		</TooltipProvider>
	);
}

function CanvasHeaderTabList({
	activeTabId,
	onTabSelect,
	tabs,
}: {
	activeTabId?: string;
	onTabSelect?: (tabId: string) => void;
	tabs: readonly CanvasFrameHeaderTab[];
}) {
	return (
		<div
			role="tablist"
			aria-label="Инструменты рабочей области"
			className="flex min-w-0 flex-1 items-center gap-0.5 overflow-x-auto overscroll-x-contain"
		>
			{tabs.map(({ icon: Icon, id, title }) => {
				const selected = id === activeTabId;
				return (
					<button
						key={id}
						type="button"
						role="tab"
						aria-selected={selected}
						tabIndex={selected ? 0 : -1}
						onClick={() => onTabSelect?.(id)}
						className={cn(
							"text-muted-foreground focus-visible:ring-ring/50 flex h-8 shrink-0 items-center gap-1.5 rounded-lg px-2.5 text-[11px] font-medium whitespace-nowrap outline-none transition-colors focus-visible:ring-2",
							selected
								? "bg-muted text-foreground"
								: "hover:bg-muted/60 hover:text-foreground",
						)}
					>
						{Icon ? <Icon className="size-3.5" aria-hidden="true" /> : null}
						{title}
					</button>
				);
			})}
		</div>
	);
}

function CanvasTabList({
	activeTabId,
	domPrefix,
	onTabSelect,
	tabs,
}: {
	activeTabId?: string;
	domPrefix: string;
	onTabSelect?: (tabId: string) => void;
	tabs: readonly CanvasFrameTab[];
}) {
	return (
		<div
			role="tablist"
			aria-label="Открытые рабочие вкладки"
			className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto"
		>
			{tabs.map((tab, index) => {
				const selected = tab.id === activeTabId;
				return (
					<button
						key={tab.id}
						type="button"
						role="tab"
						id={`${domPrefix}-tab-${index}`}
						aria-controls={`${domPrefix}-tabpanel`}
						aria-selected={selected}
						tabIndex={selected ? 0 : -1}
						onClick={() => onTabSelect?.(tab.id)}
						onKeyDown={(event) =>
							handleTabKeyDown(event, index, tabs, domPrefix, onTabSelect)
						}
						className={cn(
							"focus-visible:ring-ring/50 h-7 max-w-48 shrink-0 truncate rounded-lg px-2.5 text-[12px] font-medium outline-none focus-visible:ring-[3px]",
							selected
								? "bg-muted text-foreground"
								: "text-muted-foreground hover:bg-muted/60 hover:text-foreground",
						)}
					>
						{tab.title}
					</button>
				);
			})}
		</div>
	);
}

function handleTabKeyDown(
	event: React.KeyboardEvent<HTMLButtonElement>,
	index: number,
	tabs: readonly CanvasFrameTab[],
	domPrefix: string,
	onTabSelect?: (tabId: string) => void,
) {
	if (tabs.length === 0) return;
	let nextIndex: number | null = null;
	if (event.key === "ArrowRight") nextIndex = (index + 1) % tabs.length;
	else if (event.key === "ArrowLeft") {
		nextIndex = (index - 1 + tabs.length) % tabs.length;
	} else if (event.key === "Home") nextIndex = 0;
	else if (event.key === "End") nextIndex = tabs.length - 1;
	if (nextIndex === null) return;
	event.preventDefault();
	const tab = tabs[nextIndex];
	onTabSelect?.(tab.id);
	window.requestAnimationFrame(() =>
		document.getElementById(`${domPrefix}-tab-${nextIndex}`)?.focus(),
	);
}

function CanvasIconAction({
	label,
	children,
	className,
	...props
}: React.ComponentProps<typeof Button> & {
	label: string;
	children: ReactNode;
}) {
	return (
		<Tooltip>
			<TooltipTrigger asChild>
				<Button
					type="button"
					variant="ghost"
					size="icon-xs"
					className={cn("text-muted-foreground size-7 rounded-lg", className)}
					{...props}
				>
					{children}
					<span className="sr-only">{label}</span>
				</Button>
			</TooltipTrigger>
			<TooltipContent side="bottom" sideOffset={6}>
				{label}
			</TooltipContent>
		</Tooltip>
	);
}
