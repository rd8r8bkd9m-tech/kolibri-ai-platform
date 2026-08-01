"use client";

import { useScrollLock } from "@assistant-ui/react";
import { cva, type VariantProps } from "class-variance-authority";
import { BrainIcon, ChevronDownIcon } from "lucide-react";
import {
	type ComponentProps,
	type CSSProperties,
	createContext,
	useCallback,
	useLayoutEffect,
	useRef,
	useState,
} from "react";
import { Collapsible, CollapsibleTrigger } from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";

const ANIMATION_DURATION = 200;

const ReasoningPreviewContext = createContext(false);

const reasoningVariants = cva("aui-reasoning-root mb-4 w-full", {
	variants: {
		variant: {
			outline: "rounded-lg border px-3 py-2",
			ghost: "",
			muted: "bg-muted/50 rounded-lg px-3 py-2",
		},
	},
	defaultVariants: {
		variant: "outline",
	},
});

export type ReasoningRootProps = Omit<
	ComponentProps<typeof Collapsible>,
	"open" | "onOpenChange"
> &
	VariantProps<typeof reasoningVariants> & {
		open?: boolean;
		onOpenChange?: (open: boolean) => void;
		defaultOpen?: boolean;
		/**
		 * Whether the reasoning is currently streaming. When provided, it
		 * supersedes `defaultOpen`: the disclosure auto-opens while streaming
		 * with a bottom-pinned live preview, auto-collapses when streaming
		 * ends, and the first manual toggle takes over the open/close state
		 * permanently. The live preview keeps following the newest tokens while
		 * the disclosure is open during streaming, even after a manual toggle,
		 * and pauses while the reader is scrolled up.
		 */
		streaming?: boolean;
	};

function ReasoningRoot({
	className,
	variant,
	open: controlledOpen,
	onOpenChange: controlledOnOpenChange,
	defaultOpen = false,
	streaming,
	children,
	...props
}: ReasoningRootProps) {
	const collapsibleRef = useRef<HTMLDivElement>(null);
	const initialOpenRef = useRef(defaultOpen);
	const [userOpen, setUserOpen] = useState<boolean | null>(null);
	const lockScroll = useScrollLock(collapsibleRef, ANIMATION_DURATION);

	const isControlled = controlledOpen !== undefined;
	const isOpen = isControlled
		? controlledOpen
		: (userOpen ?? streaming ?? initialOpenRef.current);
	const isPreview = streaming === true && isOpen;

	const prevStreamingRef = useRef(streaming);
	useLayoutEffect(() => {
		if (prevStreamingRef.current === streaming) return;
		prevStreamingRef.current = streaming;
		if (!isControlled && userOpen === null) lockScroll();
	}, [streaming, isControlled, userOpen, lockScroll]);

	const handleOpenChange = useCallback(
		(open: boolean) => {
			lockScroll();
			if (!isControlled) {
				setUserOpen(open);
			}
			controlledOnOpenChange?.(open);
		},
		[lockScroll, isControlled, controlledOnOpenChange],
	);

	return (
		<Collapsible
			ref={collapsibleRef}
			data-slot="reasoning-root"
			data-variant={variant}
			open={isOpen}
			onOpenChange={handleOpenChange}
			className={cn(
				"group/reasoning-root",
				reasoningVariants({ variant, className }),
			)}
			style={
				{ "--animation-duration": `${ANIMATION_DURATION}ms` } as CSSProperties
			}
			{...props}
		>
			<ReasoningPreviewContext.Provider value={isPreview}>
				{children}
			</ReasoningPreviewContext.Provider>
		</Collapsible>
	);
}

function ReasoningFade({
	side = "bottom",
	className,
	...props
}: ComponentProps<"div"> & { side?: "top" | "bottom" }) {
	if (side === "top") {
		return (
			<div
				data-slot="reasoning-fade"
				className={cn(
					"aui-reasoning-fade pointer-events-none absolute inset-x-0 top-0 z-10 h-8",
					"bg-[linear-gradient(to_bottom,var(--color-background),transparent)]",
					"group-data-[variant=muted]/reasoning-root:bg-[linear-gradient(to_bottom,hsl(var(--muted)/0.5),transparent)]",
					"fade-in-0 animate-in",
					"duration-(--animation-duration)",
					className,
				)}
				{...props}
			/>
		);
	}

	return (
		<div
			data-slot="reasoning-fade"
			className={cn(
				"aui-reasoning-fade pointer-events-none absolute inset-x-0 bottom-0 z-10 h-8",
				"bg-[linear-gradient(to_top,var(--color-background),transparent)]",
				"group-data-[variant=muted]/reasoning-root:bg-[linear-gradient(to_top,hsl(var(--muted)/0.5),transparent)]",
				"fade-in-0 animate-in",
				"duration-(--animation-duration)",
				className,
			)}
			{...props}
		/>
	);
}

function ReasoningTrigger({
	active,
	duration,
	label = "Ход выполнения",
	className,
	...props
}: ComponentProps<typeof CollapsibleTrigger> & {
	active?: boolean;
	duration?: number;
	label?: string;
}) {
	const durationText = duration ? ` (${duration}s)` : "";

	return (
		<CollapsibleTrigger
			data-slot="reasoning-trigger"
			className={cn(
				"aui-reasoning-trigger group/trigger text-muted-foreground hover:text-foreground flex max-w-[75%] origin-left items-center gap-2 py-1.5 text-sm transition-[color,scale] active:scale-[0.98]",
				className,
			)}
			{...props}
		>
			<BrainIcon
				data-slot="reasoning-trigger-icon"
				className="aui-reasoning-trigger-icon size-4 shrink-0"
			/>
			<span
				data-slot="reasoning-trigger-label"
				className="aui-reasoning-trigger-label-wrapper relative inline-block leading-none tabular-nums"
			>
				<span>
					{label}
					{durationText}
				</span>
				{active ? (
					<span
						aria-hidden
						data-slot="reasoning-trigger-shimmer"
						className="aui-reasoning-trigger-shimmer shimmer pointer-events-none absolute inset-0 motion-reduce:animate-none"
					>
						{label}
						{durationText}
					</span>
				) : null}
			</span>
			<ChevronDownIcon
				data-slot="reasoning-trigger-chevron"
				className={cn(
					"aui-reasoning-trigger-chevron mt-0.5 size-4 shrink-0",
					"transition-transform duration-(--animation-duration) ease-[cubic-bezier(0.32,0.72,0,1)] motion-reduce:transition-none",
					"-rotate-90",
					"group-data-open/trigger:rotate-0",
					"group-data-panel-open/trigger:rotate-0",
				)}
			/>
		</CollapsibleTrigger>
	);
}

export {
	ReasoningFade,
	ReasoningPreviewContext,
	ReasoningRoot,
	ReasoningTrigger,
	reasoningVariants,
};
