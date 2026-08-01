"use client";

import type { ComponentProps } from "react";
import { Button } from "@/components/ui/button";
import {
	Tooltip,
	TooltipContent,
	TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

export type ChromeActionButtonProps = ComponentProps<typeof Button> & {
	label: string;
	shortcut?: string;
	tooltipSide?: "top" | "bottom" | "left" | "right";
	tooltipSideOffset?: number;
	tooltipClassName?: string;
	iconWrapperClassName?: string;
	iconOnly?: boolean;
};

export function ChromeActionButton({
	children,
	className,
	iconOnly = false,
	label,
	shortcut,
	tooltipSide = "bottom",
	tooltipSideOffset = 8,
	tooltipClassName,
	iconWrapperClassName,
	disabled,
	...props
}: ChromeActionButtonProps) {
	const iconOnlyButton =
		iconOnly && children ? (
			<span className={cn("inline-flex shrink-0", iconWrapperClassName)}>
				{children}
			</span>
		) : (
			children
		);

	const content = (
		<Button
			type="button"
			variant="ghost"
			className={cn(className)}
			disabled={disabled}
			{...props}
		>
			{iconOnlyButton}
			{iconOnly ? <span className="sr-only">{label}</span> : null}
		</Button>
	);

	return (
		<Tooltip>
			<TooltipTrigger asChild>
				{disabled ? (
					<span className="inline-flex cursor-default">{content}</span>
				) : (
					content
				)}
			</TooltipTrigger>
			<TooltipContent
				side={tooltipSide}
				sideOffset={tooltipSideOffset}
				className={cn("text-[13px]", tooltipClassName)}
			>
				<span className="flex items-center gap-3">
					<span>{label}</span>
					{shortcut ? (
						<kbd className="bg-muted text-muted-foreground rounded px-1.5 py-0.5 font-sans text-[11px] leading-none">
							{shortcut}
						</kbd>
					) : null}
				</span>
			</TooltipContent>
		</Tooltip>
	);
}
