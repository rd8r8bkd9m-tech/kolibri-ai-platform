"use client";

import { type ComponentProps, useContext, useEffect, useRef } from "react";
import {
	ReasoningFade,
	ReasoningPreviewContext,
} from "@/components/assistant-ui/reasoning-primitives";
import { CollapsibleContent } from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";

function ReasoningContent({
	className,
	children,
	...props
}: ComponentProps<typeof CollapsibleContent>) {
	return (
		<CollapsibleContent
			data-slot="reasoning-content"
			className={cn(
				"aui-reasoning-content text-muted-foreground relative overflow-hidden text-sm outline-none",
				"group/collapsible-content ease-[cubic-bezier(0.32,0.72,0,1)] motion-reduce:animate-none",
				"data-closed:animate-collapsible-up",
				"data-open:animate-collapsible-down",
				"data-closed:fill-mode-forwards",
				"data-closed:pointer-events-none",
				"data-open:duration-(--animation-duration)",
				"data-closed:duration-(--animation-duration)",
				className,
			)}
			{...props}
		>
			<ReasoningFade side="top" />
			{children}
			{useContext(ReasoningPreviewContext) ? <ReasoningFade /> : null}
		</CollapsibleContent>
	);
}

function ReasoningText({
	className,
	children,
	...props
}: ComponentProps<"div">) {
	const isPreview = useContext(ReasoningPreviewContext);
	const scrollRef = useRef<HTMLDivElement>(null);
	const contentRef = useRef<HTMLDivElement>(null);

	useEffect(() => {
		if (!isPreview) return;
		const scrollEl = scrollRef.current;
		const contentEl = contentRef.current;
		if (!scrollEl || !contentEl) return;

		let pinned = true;
		let lastScrollTop = scrollEl.scrollTop;
		let lastScrollHeight = scrollEl.scrollHeight;
		const isAtBottom = () =>
			Math.abs(
				scrollEl.scrollHeight - scrollEl.scrollTop - scrollEl.clientHeight,
			) <= 1 || scrollEl.scrollHeight <= scrollEl.clientHeight;

		const pin = () => {
			if (!pinned) return;
			scrollEl.scrollTop = scrollEl.scrollHeight;
		};
		// A pin's own scroll event can arrive after new content grew the scroll
		// height and read as "not at bottom"; only an upward move at unchanged
		// scroll height is user intent.
		const onScroll = () => {
			if (isAtBottom()) {
				pinned = true;
			} else if (
				scrollEl.scrollTop < lastScrollTop &&
				scrollEl.scrollHeight === lastScrollHeight
			) {
				pinned = false;
			}
			lastScrollTop = scrollEl.scrollTop;
			lastScrollHeight = scrollEl.scrollHeight;
		};

		pin();
		scrollEl.addEventListener("scroll", onScroll);
		const observer = new ResizeObserver(pin);
		observer.observe(contentEl);
		return () => {
			scrollEl.removeEventListener("scroll", onScroll);
			observer.disconnect();
		};
	}, [isPreview]);

	return (
		<div
			ref={scrollRef}
			data-slot="reasoning-text"
			className={cn(
				"aui-reasoning-text relative z-0 max-h-64 overflow-y-auto ps-6 pt-2 pb-2 leading-relaxed text-pretty",
				"transform-gpu transition-[transform,opacity] ease-[cubic-bezier(0.32,0.72,0,1)]",
				"motion-reduce:animate-none",
				"group-data-open/collapsible-content:animate-in",
				"group-data-closed/collapsible-content:animate-out",
				"group-data-open/collapsible-content:fade-in-0",
				"group-data-closed/collapsible-content:fade-out-0",
				"group-data-open/collapsible-content:slide-in-from-top-4",
				"group-data-closed/collapsible-content:slide-out-to-top-4",
				"group-data-open/collapsible-content:duration-(--animation-duration)",
				"group-data-closed/collapsible-content:duration-(--animation-duration)",
				className,
			)}
			{...props}
		>
			<div ref={contentRef} className="aui-reasoning-text-content space-y-4">
				{children}
			</div>
		</div>
	);
}

export { ReasoningContent, ReasoningText };
