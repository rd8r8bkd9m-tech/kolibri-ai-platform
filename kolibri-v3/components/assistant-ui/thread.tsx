"use client";

import { type FC } from "react";

import {
	ThreadCompactContext,
	ThreadComponentsContext,
	ThreadNavigationContext,
	type ThreadComponents,
	type ThreadProps,
	EMPTY_COMPONENTS,
} from "./thread/thread-context";
import { ThreadViewportScreen } from "./thread/layouts/thread-screen";
import { Composer } from "./thread/parts/thread-layout";

export {
	ThreadComponentsContext,
	ThreadCompactContext,
	ThreadNavigationContext,
};
export type {
	ThreadComponents,
	ThreadProps,
	ThreadGroupPart,
} from "./thread/thread-context";

export const Thread: FC<ThreadProps> = ({
	compact = false,
	components = EMPTY_COMPONENTS,
	composerPlacement = "viewport",
	onOpenAccount,
	onOpenContextPanel,
	workspaceOpen = false,
}) => {
	return (
		<ThreadNavigationContext.Provider
			value={{ onOpenAccount, onOpenContextPanel, workspaceOpen }}
		>
			<ThreadCompactContext.Provider value={compact}>
				<ThreadComponentsContext.Provider value={components}>
					<ThreadViewportScreen
						showComposer={composerPlacement === "viewport"}
					/>
				</ThreadComponentsContext.Provider>
			</ThreadCompactContext.Provider>
		</ThreadNavigationContext.Provider>
	);
};

export const ThreadComposer: FC<
	Pick<
		ThreadProps,
		"compact" | "onOpenAccount" | "onOpenContextPanel" | "workspaceOpen"
	>
> = ({
	compact = false,
	onOpenAccount,
	onOpenContextPanel,
	workspaceOpen = false,
}) => {
	return (
		<ThreadNavigationContext.Provider
			value={{ onOpenAccount, onOpenContextPanel, workspaceOpen }}
		>
			<ThreadCompactContext.Provider value={compact}>
				<Composer />
			</ThreadCompactContext.Provider>
		</ThreadNavigationContext.Provider>
	);
};

export const ThreadRoot: FC = () => {
	return <ThreadViewportScreen />;
};
