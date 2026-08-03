"use client";

import {
	createContext,
	type PropsWithChildren,
	useContext,
	useEffect,
} from "react";
import type { WorkspaceContextV1 } from "@/lib/workspace-context";

type WorkspaceContextPublisher = (context: WorkspaceContextV1 | null) => void;

const WorkspaceContextPublisherContext =
	createContext<WorkspaceContextPublisher | null>(null);

export function WorkspaceContextPublisherProvider({
	children,
	publish,
}: PropsWithChildren<{ publish: WorkspaceContextPublisher }>) {
	return (
		<WorkspaceContextPublisherContext.Provider value={publish}>
			{children}
		</WorkspaceContextPublisherContext.Provider>
	);
}

export function usePublishWorkspaceContext(context: WorkspaceContextV1) {
	const publish = useContext(WorkspaceContextPublisherContext);

	useEffect(() => {
		publish?.(context);
		return () => publish?.(null);
	}, [context, publish]);
}
