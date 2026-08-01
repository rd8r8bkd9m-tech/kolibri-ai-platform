"use client";

import { ThreadListPrimitive } from "@assistant-ui/react";
import { type ComponentPropsWithoutRef, type FC } from "react";
import { cn } from "@/lib/utils";
import { uiClassTokens } from "@/components/ui/class-names";

export const ThreadListRoot: FC<
	ComponentPropsWithoutRef<typeof ThreadListPrimitive.Root>
> = ({ className, ...props }) => {
	return (
		<ThreadListPrimitive.Root
			data-slot="aui_thread-list-root"
			className={cn(uiClassTokens.threadListItems, className)}
			{...props}
		/>
	);
};
