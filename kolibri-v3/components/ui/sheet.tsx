"use client";

import { XIcon } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/utils";

type SheetSide = "top" | "bottom" | "left" | "right";

interface SheetProps {
	open: boolean;
	onOpenChange: (open: boolean) => void;
	children: React.ReactNode;
}

function Sheet({ open, onOpenChange, children }: SheetProps) {
	React.useEffect(() => {
		if (open) {
			const handleEscape = (e: KeyboardEvent) => {
				if (e.key === "Escape") onOpenChange(false);
			};
			document.addEventListener("keydown", handleEscape);
			return () => document.removeEventListener("keydown", handleEscape);
		}
	}, [open, onOpenChange]);

	if (!open) return null;

	return (
		<div data-slot="sheet" className="fixed inset-0 z-50">
			{children}
		</div>
	);
}

function SheetOverlay({
	className,
	onClick,
	...props
}: React.ComponentProps<"div">) {
	return (
		<div
			data-slot="sheet-overlay"
			className={cn(
				"fixed inset-0 bg-black/50 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:animate-in data-[state=open]:fade-in-0",
				className,
			)}
			onClick={onClick}
			{...props}
		/>
	);
}

const sheetSideClasses: Record<SheetSide, string> = {
	top: "inset-x-0 top-0 border-b data-[state=closed]:slide-out-to-top data-[state=open]:slide-in-from-top",
	bottom: "inset-x-0 bottom-0 border-t data-[state=closed]:slide-out-to-bottom data-[state=open]:slide-in-from-bottom",
	left: "inset-y-0 left-0 h-full w-3/4 border-r data-[state=closed]:slide-out-to-left data-[state=open]:slide-in-from-left sm:max-w-sm",
	right: "inset-y-0 right-0 h-full w-3/4 border-l data-[state=closed]:slide-out-to-right data-[state=open]:slide-in-from-right sm:max-w-sm",
};

interface SheetContentProps extends React.ComponentProps<"div"> {
	side?: SheetSide;
	onClose?: () => void;
	showCloseButton?: boolean;
}

function SheetContent({
	className,
	children,
	side = "right",
	onClose,
	showCloseButton = true,
	...props
}: SheetContentProps) {
	return (
		<>
			<SheetOverlay onClick={onClose} />
			<div
				data-slot="sheet-content"
				className={cn(
					"fixed z-50 bg-background p-6 shadow-lg transition ease-in-out data-[state=closed]:duration-300 data-[state=open]:duration-500",
					sheetSideClasses[side],
					className,
				)}
				{...props}
			>
				{children}
				{showCloseButton && onClose && (
					<button
						onClick={onClose}
						className="absolute top-4 right-4 rounded-xs opacity-70 ring-offset-background transition-opacity hover:opacity-100 focus:ring-2 focus:ring-ring focus:ring-offset-2 focus:outline-hidden disabled:pointer-events-none"
					>
						<XIcon className="size-4" />
						<span className="sr-only">Close</span>
					</button>
				)}
			</div>
		</>
	);
}

function SheetHeader({ className, ...props }: React.ComponentProps<"div">) {
	return (
		<div
			data-slot="sheet-header"
			className={cn("flex flex-col gap-2 text-center sm:text-left", className)}
			{...props}
		/>
	);
}

function SheetFooter({ className, ...props }: React.ComponentProps<"div">) {
	return (
		<div
			data-slot="sheet-footer"
			className={cn(
				"flex flex-col-reverse gap-2 sm:flex-row sm:justify-end",
				className,
			)}
			{...props}
		/>
	);
}

function SheetTitle({ className, ...props }: React.ComponentProps<"h2">) {
	return (
		<h2
			data-slot="sheet-title"
			className={cn("text-lg font-semibold text-foreground", className)}
			{...props}
		/>
	);
}

function SheetDescription({
	className,
	...props
}: React.ComponentProps<"p">) {
	return (
		<p
			data-slot="sheet-description"
			className={cn("text-sm text-muted-foreground", className)}
			{...props}
		/>
	);
}

export {
	Sheet,
	SheetContent,
	SheetDescription,
	SheetFooter,
	SheetHeader,
	SheetOverlay,
	SheetTitle,
};
