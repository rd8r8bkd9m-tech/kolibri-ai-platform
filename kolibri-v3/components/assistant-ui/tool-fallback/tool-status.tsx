import type { ToolCallMessagePartStatus } from "@assistant-ui/react";
import { useToolCallElapsed } from "@assistant-ui/react";
import type { ComponentProps } from "react";
import { getToolStatusPresentation } from "@/components/assistant-ui/tool-fallback/tool-presentation";
import { cn } from "@/lib/utils";

function formatToolDuration(ms: number) {
	if (ms < 1000) return "<1s";
	const seconds = ms / 1000;
	if (seconds < 10) return `${(Math.floor(seconds * 10) / 10).toFixed(1)}s`;
	if (seconds < 60) return `${Math.floor(seconds)}s`;
	return `${Math.floor(seconds / 60)}m ${Math.floor(seconds % 60)}s`;
}

export function ToolFallbackDuration({
	className,
	...props
}: ComponentProps<"span">) {
	const elapsedMs = useToolCallElapsed();
	if (elapsedMs === undefined) return null;

	return (
		<span
			data-slot="tool-fallback-duration"
			className={cn(
				"aui-tool-fallback-duration text-muted-foreground text-xs tabular-nums",
				className,
			)}
			{...props}
		>
			{formatToolDuration(elapsedMs)}
		</span>
	);
}

type ToolStatusProps = {
	toolName: string;
	status?: ToolCallMessagePartStatus;
	showDuration?: boolean;
	className?: string;
	iconClassName?: string;
	labelClassName?: string;
};

export function ToolStatus({
	toolName,
	status,
	showDuration = false,
	className,
	iconClassName,
	labelClassName,
}: ToolStatusProps) {
	const {
		icon: Icon,
		isCancelled,
		isRunning,
		label,
	} = getToolStatusPresentation(toolName, status);

	return (
		<>
			<Icon
				aria-hidden
				className={cn(
					"size-4 shrink-0",
					isCancelled && "text-muted-foreground",
					isRunning && "animate-spin [animation-duration:0.6s]",
					iconClassName,
				)}
			/>
			<span
				className={cn(
					"relative inline-block text-start leading-none",
					isCancelled && "text-muted-foreground line-through",
					className,
				)}
			>
				<span className={labelClassName}>{label}</span>
				{isRunning ? (
					<span
						aria-hidden
						className="shimmer pointer-events-none absolute inset-0 motion-reduce:animate-none"
					>
						{label}
					</span>
				) : null}
			</span>
			{showDuration ? <ToolFallbackDuration /> : null}
		</>
	);
}

export function ProductToolStatus({
	toolName,
	status,
}: Pick<ToolStatusProps, "toolName" | "status">) {
	const { label } = getToolStatusPresentation(toolName, status);
	return (
		<div
			data-slot="product-tool-status"
			className="text-muted-foreground flex w-fit items-center gap-2 py-1.5 text-sm"
			role="status"
			aria-label={label}
		>
			<ToolStatus toolName={toolName} status={status} showDuration />
		</div>
	);
}
