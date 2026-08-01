"use client";

import { LoaderCircle, type LucideIcon } from "lucide-react";
import type { ComponentProps, ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

export type AdminStatusTone = "ready" | "running" | "failed" | "neutral";

export function AdminCard({ className, ...props }: ComponentProps<"article">) {
	return (
		<article
			className={cn("rounded-2xl border bg-card p-4", className)}
			{...props}
		/>
	);
}

export function AdminDatum({
	label,
	value,
}: {
	label: ReactNode;
	value: ReactNode;
}) {
	return (
		<div className="min-w-0">
			<dt className="text-muted-foreground">{label}</dt>
			<dd className="mt-0.5 break-words font-medium">{value}</dd>
		</div>
	);
}

export function AdminStatusBadge({
	label,
	tone,
	state,
	className,
}: {
	label: ReactNode;
	tone?: AdminStatusTone;
	state?: AdminStatusTone;
	className?: string;
}) {
	const resolvedTone = tone ?? state ?? "neutral";
	return (
		<span
			className={cn(
				"shrink-0 rounded-full border px-2 py-1 text-[10px] font-medium",
				resolvedTone === "ready" &&
					"border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
				resolvedTone === "running" &&
					"border-blue-500/30 bg-blue-500/10 text-blue-700 dark:text-blue-300",
				resolvedTone === "failed" &&
					"border-destructive/30 bg-destructive/10 text-destructive",
				resolvedTone === "neutral" && "text-muted-foreground",
				className,
			)}
		>
			{label}
		</span>
	);
}

export function AdminMetricCard({
	icon: Icon,
	label,
	value,
	compact = false,
}: {
	icon?: LucideIcon;
	label: ReactNode;
	value: ReactNode;
	compact?: boolean;
}) {
	return compact ? (
		<div className="rounded-xl border px-3 py-2">
			<p className="text-muted-foreground text-[12px]">{label}</p>
			<p className="mt-1 text-[13px] font-semibold">{value}</p>
		</div>
	) : (
		<AdminCard>
			{Icon ? (
				<Icon className="text-muted-foreground size-4" aria-hidden="true" />
			) : null}
			<p className="mt-3 text-xl font-semibold">{value}</p>
			<p className="text-muted-foreground mt-1 text-[11px]">{label}</p>
		</AdminCard>
	);
}

export function AdminCompactMetric(
	props: Omit<ComponentProps<typeof AdminMetricCard>, "compact">,
) {
	return <AdminMetricCard {...props} compact />;
}

export function AdminEmptyState({
	children,
	text,
}: {
	children?: ReactNode;
	text?: ReactNode;
}) {
	return (
		<p className="text-muted-foreground rounded-2xl border p-4 text-[12px]">
			{children ?? text}
		</p>
	);
}

export function AdminTextField({
	disabled,
	inputMode,
	label,
	onChange,
	placeholder,
	value,
}: {
	disabled?: boolean;
	inputMode?: "numeric";
	label: string;
	onChange: (value: string) => void;
	placeholder?: string;
	value: string;
}) {
	return (
		<label className="block text-[11px] font-medium">
			{label}
			<Input
				value={value}
				disabled={disabled}
				inputMode={inputMode}
				placeholder={placeholder}
				onChange={(event) => onChange(event.target.value)}
				className="mt-1.5 h-9 rounded-lg text-[12px] shadow-none"
			/>
		</label>
	);
}

export function AdminStatusMessage({
	failed,
	message,
}: {
	failed: boolean;
	message: string | null;
}) {
	if (!message) return null;
	return (
		<p
			className={cn(
				"mt-3 text-[11px]",
				failed ? "text-destructive" : "text-muted-foreground",
			)}
			role={failed ? "alert" : "status"}
		>
			{message}
		</p>
	);
}

export function AdminLoadMoreButton({
	children,
	cursor,
	loading,
	className,
	...props
}: Omit<ComponentProps<typeof Button>, "children"> & {
	children: ReactNode;
	cursor: string | null;
	loading: boolean;
}) {
	if (!cursor) return <span className={className} />;
	return (
		<Button
			type="button"
			variant="outline"
			size="sm"
			className={cn("w-fit rounded-lg shadow-none", className)}
			{...props}
		>
			{loading ? (
				<LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
			) : null}
			{children}
		</Button>
	);
}
