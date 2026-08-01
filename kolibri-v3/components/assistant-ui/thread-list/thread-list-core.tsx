"use client";

import { useAuiState } from "@assistant-ui/react";
import { type FC, useState } from "react";

import { ThreadListItems } from "@/components/assistant-ui/thread-list/thread-list-items";
import { ThreadListNew } from "@/components/assistant-ui/thread-list/thread-list-new";
import { ThreadListRoot } from "@/components/assistant-ui/thread-list/thread-list-root";
import { ThreadListSearch } from "@/components/assistant-ui/thread-list/thread-list-search";

export const ThreadList: FC = () => {
	const [search, setSearch] = useState("");
	const hasThreads = useAuiState((s) => s.threads.threadIds.length > 0);

	return (
		<ThreadListRoot>
			<ThreadListNew />
			{hasThreads && (
				<ThreadListSearch value={search} onValueChange={setSearch} />
			)}
			<ThreadListItems searchQuery={hasThreads ? search : ""} />
		</ThreadListRoot>
	);
};
