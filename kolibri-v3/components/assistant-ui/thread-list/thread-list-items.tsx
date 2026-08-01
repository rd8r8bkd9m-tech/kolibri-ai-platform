"use client";

import { AuiIf, ThreadListPrimitive } from "@assistant-ui/react";
import type { ComponentPropsWithoutRef } from "react";
import { type FC } from "react";
import { ThreadListContainer } from "@/components/ui/shared-wrappers";
import { uiClassTokens } from "@/components/ui/class-names";
import { Skeleton } from "@/components/ui/skeleton";

import {
	ArchivedThreadListItems,
	ThreadListItemGroups,
} from "./thread-list-groups";

export const ThreadListItems: FC<
	ComponentPropsWithoutRef<"div"> & { searchQuery?: string }
> = ({ className, searchQuery = "", ...props }) => {
	return (
		<ThreadListContainer
			data-slot="aui_thread-list-items"
			className={className}
			{...props}
		>
			<AuiIf condition={(s) => s.threads.isLoading}>
				<ThreadListSkeleton />
			</AuiIf>
			<AuiIf condition={(s) => !s.threads.isLoading}>
				<ThreadListItemGroups searchQuery={searchQuery} />
				<ArchivedThreadListItems searchQuery={searchQuery} />
			</AuiIf>
		</ThreadListContainer>
	);
};

const ThreadListSkeleton: FC = () => {
	return (
		<div className={uiClassTokens.threadListSkeletonRow}>
			{Array.from({ length: 5 }, (_, i) => (
				<div
					key={i}
					role="status"
					aria-label="Загрузка задач"
					data-slot="aui_thread-list-skeleton-wrapper"
					className={uiClassTokens.threadListSkeletonItem}
				>
					<Skeleton
						data-slot="aui_thread-list-skeleton"
						className={uiClassTokens.threadListSkeletonTile}
					/>
				</div>
			))}
		</div>
	);
};
