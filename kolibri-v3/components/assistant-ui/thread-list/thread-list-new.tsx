"use client";

import { ThreadListPrimitive } from "@assistant-ui/react";
import { PlusIcon } from "lucide-react";
import type { ComponentPropsWithoutRef } from "react";
import { forwardRef } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { uiClassTokens } from "@/components/ui/class-names";

export const ThreadListNew = forwardRef<
	HTMLButtonElement,
	ComponentPropsWithoutRef<typeof Button> & { labelClassName?: string }
>(({ className, labelClassName, children, ...props }, ref) => {
	return (
		<ThreadListPrimitive.New asChild>
			<Button
				ref={ref}
				variant="ghost"
				data-slot="aui_thread-list-new"
				className={cn(
					uiClassTokens.threadListNewButton,
					className,
				)}
				{...props}
			>
				{children ?? (
					<>
						<PlusIcon
							data-slot="aui_thread-list-new-icon"
							className="size-4 shrink-0"
						/>
						<span
							data-slot="aui_thread-list-new-label"
							className={cn("whitespace-nowrap", labelClassName)}
						>
							Новая задача
						</span>
					</>
				)}
			</Button>
		</ThreadListPrimitive.New>
	);
});

ThreadListNew.displayName = "ThreadListNew";
