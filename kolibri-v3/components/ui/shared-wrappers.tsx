"use client";

import * as React from "react";

import { cn } from "@/lib/utils";
import { uiClassTokens } from "@/components/ui/class-names";

type ContainerBaseProps = React.ComponentProps<"div">;

export function PanelContainer({ className, ...props }: ContainerBaseProps) {
	return (
		<div className={cn(uiClassTokens.generativeUIPanel, className)} {...props} />
	);
}

export function DashedMutedPanel({
	className,
	...props
}: React.ComponentProps<"div">) {
	return (
		<div
			className={cn(uiClassTokens.generativeFallbackPanel, className)}
			{...props}
		/>
	);
}

export function IconActionLink({
	className,
	children,
	...props
}: Omit<React.ComponentPropsWithoutRef<"a">, "className"> & {
	className?: string;
	children: React.ReactNode;
}) {
	return (
		<a className={cn(uiClassTokens.iconActionButton, className)} {...props}>
			{children}
		</a>
	);
}

export function SidebarDestinationButton({
	className,
	...props
}: React.ComponentProps<"button">) {
	return (
		<button
			className={cn(uiClassTokens.sidebarDestinationButton, className)}
			{...props}
		/>
	);
}

export function WorkspaceSidebarBody({
	className,
	...props
}: React.ComponentProps<"div">) {
	return (
		<div className={cn(uiClassTokens.sidebarBody, className)} {...props} />
	);
}

export function WorkspaceSidebarSectionHeading({
	className,
	...props
}: React.ComponentProps<"h2">) {
	return (
		<h2
			className={cn(uiClassTokens.sidebarSectionHeading, className)}
			{...props}
		/>
	);
}

export function ThreadListItemMetaCard({
	className,
	...props
}: React.ComponentProps<"div">) {
	return (
		<div
			className={cn(uiClassTokens.threadListItemMetaCard, className)}
			{...props}
		/>
	);
}

export function ThreadListContainer({
	className,
	...props
}: React.ComponentProps<"div">) {
	return (
		<div className={cn(uiClassTokens.threadListItems, className)} {...props} />
	);
}

export function ThreadRoot({
	className,
	...props
}: React.ComponentProps<"div">) {
	return <div className={cn(uiClassTokens.threadRoot, className)} {...props} />;
}

export function ThreadViewport({
	className,
	...props
}: React.ComponentProps<"div">) {
	return <div className={cn(uiClassTokens.threadViewport, className)} {...props} />;
}

export function ThreadViewportContent({
	className,
	...props
}: React.ComponentProps<"div">) {
	return (
		<div
			className={cn(uiClassTokens.threadViewportContent, className)}
			{...props}
		/>
	);
}

export function ThreadViewportFooter({
	className,
	...props
}: React.ComponentProps<"div">) {
	return (
		<div
			className={cn(uiClassTokens.threadViewportFooter, className)}
			{...props}
		/>
	);
}

export function ThreadComposer({
	className,
	...props
}: React.ComponentProps<"div">) {
	return (
		<div className={cn(uiClassTokens.threadComposerRoot, className)} {...props} />
	);
}

export function ThreadComposerShell({
	className,
	...props
}: React.ComponentProps<"div">) {
	return (
		<div
			className={cn(uiClassTokens.threadComposerShell, className)}
			{...props}
		/>
	);
}

export function ThreadComposerActionRow({
	className,
	...props
}: React.ComponentProps<"div">) {
	return (
		<div
			className={cn(uiClassTokens.threadComposerActionRow, className)}
			{...props}
		/>
	);
}

export function WorkspaceSidebarShell({
	className,
	...props
}: React.ComponentProps<"aside">) {
	return (
		<aside
			className={cn(uiClassTokens.workspaceSidebarShell, className)}
			{...props}
		/>
	);
}
