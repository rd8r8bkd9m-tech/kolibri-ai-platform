"use client";

import type { LucideIcon } from "lucide-react";
import type { ComponentProps } from "react";
import { ChromeActionButton } from "@/components/kolibri-shell/chrome-action-button";
import { Button } from "@/components/ui/button";
import { uiClassTokens } from "@/components/ui/class-names";
import { cn } from "@/lib/utils";
import { type WorkspaceSidebarDestination } from "./constants";

export type SidebarChromeButtonProps = ComponentProps<typeof Button> & {
	label: string;
	shortcut?: string;
};

export function SidebarChromeButton({
	children,
	className,
	disabled,
	label,
	shortcut,
	...props
}: SidebarChromeButtonProps) {
	return (
		<ChromeActionButton
			label={label}
			shortcut={shortcut}
			iconOnly
			size="icon-sm"
			disabled={disabled}
			className={cn(
				"text-muted-foreground rounded-lg hover:bg-sidebar-accent hover:text-sidebar-foreground",
				className,
			)}
			tooltipSideOffset={5}
			tooltipClassName="border bg-popover px-2.5 py-1.5 text-popover-foreground shadow-md [&>svg]:hidden"
			{...props}
		>
			{children}
		</ChromeActionButton>
	);
}

export type SidebarDestinationProps = ComponentProps<"button"> & {
	active?: boolean;
	icon: LucideIcon;
	id: WorkspaceSidebarDestination;
	label: string;
	"data-canvas-launcher"?: string;
	launcherId?: string;
	onClick?: () => void;
};

export function SidebarDestination({
	active = false,
	icon: Icon,
	id,
	label,
	onClick,
	className,
	["data-canvas-launcher"]: dataCanvasLauncher,
	launcherId: ignoredLauncherId,
	...buttonProps
}: SidebarDestinationProps) {
	const normalizedLauncherId = ignoredLauncherId ?? dataCanvasLauncher;

	const destinationButton = (
		<Button
			type="button"
			variant="ghost"
			onClick={onClick}
			data-slot="workspace-sidebar-destination"
			data-destination={id}
			aria-current={active ? "page" : undefined}
			className={cn(
				uiClassTokens.sidebarDestinationButton,
				active &&
					"bg-[#d9e7fc] text-sidebar-accent-foreground hover:bg-[#d9e7fc] dark:bg-sky-900/45",
				className,
			)}
			data-canvas-launcher={normalizedLauncherId}
			{...buttonProps}
		>
			<Icon className="size-[17px]" />
			<span className="truncate">{label}</span>
		</Button>
	);

	return destinationButton;
}
