"use client";

import { SearchIcon } from "lucide-react";
import { type ComponentPropsWithoutRef, forwardRef } from "react";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { uiClassTokens } from "@/components/ui/class-names";

export const ThreadListSearch = forwardRef<
	HTMLInputElement,
	Omit<ComponentPropsWithoutRef<"input">, "value" | "onChange"> & {
		value: string;
		onValueChange: (value: string) => void;
	}
>(({ className, value, onValueChange, ...props }, ref) => {
	return (
		<div data-slot="aui_thread-list-search" className={uiClassTokens.threadListSearch}>
			<SearchIcon
				data-slot="aui_thread-list-search-icon"
				className={uiClassTokens.threadListSearchIcon}
			/>
			<Input
				ref={ref}
				type="search"
				value={value}
				onChange={(event) => onValueChange(event.target.value)}
				aria-label="Поиск по задачам"
				placeholder="Поиск"
				className={cn(
					uiClassTokens.threadListSearchInput,
					className,
				)}
				{...props}
			/>
		</div>
	);
});

ThreadListSearch.displayName = "ThreadListSearch";
