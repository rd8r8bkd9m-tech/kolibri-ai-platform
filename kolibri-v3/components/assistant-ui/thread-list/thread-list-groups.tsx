"use client";

import { ThreadListPrimitive, useAuiState } from "@assistant-ui/react";
import { ArchiveIcon } from "lucide-react";
import { type FC, Fragment, useMemo } from "react";
import { uiClassTokens } from "@/components/ui/class-names";
import { ThreadListItem } from "@/components/assistant-ui/thread-list/thread-list-item";
import {
	getThreadDateGroupLabel,
	getThreadItemIndicesByQuery,
	ThreadListItemLike,
	normalizeThreadListSearchQuery,
} from "./thread-list-utils";

type ThreadListGroup = { label: string; indices: number[] };

export const ThreadListItemGroups: FC<{ searchQuery?: string }> = ({
	searchQuery = "",
}) => {
	const threadIds = useAuiState((s) => s.threads.threadIds);
	const threadItems = useAuiState(
		(s): readonly ThreadListItemLike[] =>
			(s.threads.threadItems as readonly ThreadListItemLike[] | undefined) ?? [],
	);

	const query = normalizeThreadListSearchQuery(searchQuery);
	const filteredIndices = useMemo(
		() => getThreadItemIndicesByQuery(threadIds, threadItems, query),
		[threadIds, threadItems, query],
	);

	const { groups } = useMemo(() => {
		const itemsById = new Map(threadItems.map((item) => [item.id, item]));
		const dates = threadIds.map((id) => itemsById.get(id)?.lastMessageAt);

		if (!filteredIndices.some((index) => dates[index])) {
			return { groups: null as ThreadListGroup[] | null };
		}

		const now = new Date();
		const startOfToday = new Date(
			now.getFullYear(),
			now.getMonth(),
			now.getDate(),
		).getTime();
		const time = (index: number) => dates[index]?.getTime() ?? Number.MAX_SAFE_INTEGER;
		const sorted = [...filteredIndices].sort((a, b) => time(b) - time(a));

		const pinned = sorted.filter(
			(index: number) =>
				itemsById.get(threadIds[index]!)?.custom?.pinned === true,
		);
		const unpinned = sorted.filter(
			(index: number) =>
				itemsById.get(threadIds[index]!)?.custom?.pinned !== true,
		);
		const result: ThreadListGroup[] = pinned.length
			? [{ label: "Закреплённые", indices: pinned }]
			: [];
		for (const index of unpinned) {
			const label = getThreadDateGroupLabel(dates[index], startOfToday);
			const lastGroup = result[result.length - 1];
			if (lastGroup?.label === label) {
				lastGroup.indices.push(index);
			} else {
				result.push({ label, indices: [index] });
			}
		}
		return { groups: result };
	}, [threadIds, threadItems, query, filteredIndices]);

	if (query && filteredIndices.length === 0) {
		return (
			<div
				data-slot="aui_thread-list-empty"
				className={uiClassTokens.threadListItemsEmpty}
			>
				Ничего не найдено
			</div>
		);
	}

	if (!groups) {
		return filteredIndices.map((index) => (
			<ThreadListPrimitive.ItemByIndex
				key={threadIds[index]}
				index={index}
				components={{ ThreadListItem }}
			/>
		));
	}

	return groups.map((group: ThreadListGroup) => (
		<Fragment key={group.label}>
			<div
				data-slot="aui_thread-list-group-label"
				className={uiClassTokens.threadListGroupLabel}
			>
				{group.label}
			</div>
			{group.indices.map((index: number) => (
				<ThreadListPrimitive.ItemByIndex
					key={threadIds[index]}
					index={index}
					components={{ ThreadListItem }}
				/>
			))}
		</Fragment>
	));
};

export const ArchivedThreadListItems: FC<{ searchQuery?: string }> = ({
	searchQuery = "",
}) => {
	const archivedThreadIds = useAuiState((s) => s.threads.archivedThreadIds);
	const threadItems = useAuiState(
		(s): readonly ThreadListItemLike[] =>
			(s.threads.threadItems as readonly ThreadListItemLike[] | undefined) ?? [],
	);
	const query = normalizeThreadListSearchQuery(searchQuery);
	const visibleIndices = useMemo(() => {
		return getThreadItemIndicesByQuery(
			archivedThreadIds,
			threadItems,
			query,
		);
	}, [archivedThreadIds, query, threadItems]);

	if (visibleIndices.length === 0) return null;

	return (
		<details
			data-slot="aui_thread-list-archive"
			className={uiClassTokens.threadListArchiveDetails}
			open={query ? true : undefined}
		>
			<summary className={uiClassTokens.threadListArchiveSummary}>
				<ArchiveIcon className="mr-2 size-3.5" />
				<span className="flex-1">Архив</span>
				<span className={uiClassTokens.threadListArchiveBadge}>
					{visibleIndices.length}
				</span>
			</summary>
			<div className={uiClassTokens.threadListArchiveItems}>
				{visibleIndices.map((index) => (
					<ThreadListPrimitive.ItemByIndex
						key={archivedThreadIds[index]}
						index={index}
						archived
						components={{ ThreadListItem }}
					/>
				))}
			</div>
		</details>
	);
};
