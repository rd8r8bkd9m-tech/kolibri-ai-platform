import type { AgentSubscriber } from "@ag-ui/client";

import {
	PET_ACTIVITY_EVENT_TYPE,
	parsePetActivityEventV1,
	projectPetActivityFromAgUiEvent,
	type PetActivityEventV1,
	type PetActivityState,
	type PetServerActivityState,
} from "./motion";

export type PetActivitySource =
	| "server-contract"
	| "ag-ui-derived"
	| "local-connection";

export type PetActivitySnapshot = {
	activity: PetActivityEventV1;
	receivedAtMs: number;
	source: PetActivitySource;
	state: PetActivityState;
};

export type PetMessageAcceptedSnapshot = {
	ordinal: number;
	receivedAtMs: number;
	runId: string;
	threadId: string;
};

type PublishPetActivityOptions = {
	receivedAtMs?: number;
	source: PetActivitySource;
	state?: PetActivityState;
};

export type PetActivityFeed = {
	clear: () => void;
	getAcceptedSnapshot: (
		threadId: string | null,
	) => PetMessageAcceptedSnapshot | null;
	getSnapshot: (threadId: string | null) => PetActivitySnapshot | null;
	publishAccepted: (snapshot: PetMessageAcceptedSnapshot) => boolean;
	publish: (
		activity: PetActivityEventV1,
		options: PublishPetActivityOptions,
	) => boolean;
	subscribe: (listener: () => void) => () => void;
};

export function createPetActivityFeed(): PetActivityFeed {
	const acceptedSnapshots = new Map<string, PetMessageAcceptedSnapshot>();
	const listeners = new Set<() => void>();
	const snapshots = new Map<string, PetActivitySnapshot>();

	return {
		clear() {
			if (snapshots.size === 0 && acceptedSnapshots.size === 0) return;
			snapshots.clear();
			acceptedSnapshots.clear();
			for (const listener of listeners) listener();
		},
		getAcceptedSnapshot(threadId) {
			return threadId ? (acceptedSnapshots.get(threadId) ?? null) : null;
		},
		getSnapshot(threadId) {
			return threadId ? (snapshots.get(threadId) ?? null) : null;
		},
		publishAccepted(snapshot) {
			const current = acceptedSnapshots.get(snapshot.threadId);
			if (current?.runId === snapshot.runId) return false;
			acceptedSnapshots.set(snapshot.threadId, snapshot);
			for (const listener of listeners) listener();
			return true;
		},
		publish(activity, options) {
			const receivedAtMs = options.receivedAtMs ?? Date.now();
			const current = snapshots.get(activity.threadId);
			if (current) {
				const sameRun = current.activity.runId === activity.runId;
				if (sameRun) {
					if (
						current.source === "server-contract" &&
						options.source === "ag-ui-derived"
					) {
						return false;
					}
					if (
						current.source === options.source &&
						activity.sequence <= current.activity.sequence
					) {
						return false;
					}
				} else {
					// `occurredAt` can originate on either the backend or this client.
					// Compare receipt order across runs so clock skew cannot revive an old
					// state or reject the first event from a new accepted run.
					if (receivedAtMs < current.receivedAtMs) return false;
				}
			}

			snapshots.set(activity.threadId, {
				activity,
				receivedAtMs,
				source: options.source,
				state: options.state ?? activity.state,
			});
			for (const listener of listeners) listener();
			return true;
		},
		subscribe(listener) {
			listeners.add(listener);
			return () => listeners.delete(listener);
		},
	};
}

const petActivityFeed = createPetActivityFeed();
let messageAcceptedOrdinal = 0;

export const clearPetActivityFeed = () => petActivityFeed.clear();
export const getPetMessageAcceptedOrdinal = () => messageAcceptedOrdinal;
export const getPetMessageAcceptedSnapshot = (threadId: string | null) =>
	petActivityFeed.getAcceptedSnapshot(threadId);
export const getPetActivitySnapshot = (threadId: string | null) =>
	petActivityFeed.getSnapshot(threadId);
export const publishPetMessageAccepted = (threadId: string, runId: string) =>
	petActivityFeed.publishAccepted({
		ordinal: ++messageAcceptedOrdinal,
		receivedAtMs: Date.now(),
		runId,
		threadId,
	});
export const subscribeToPetActivityFeed = (listener: () => void) =>
	petActivityFeed.subscribe(listener);

type PetActivitySubscriberOptions = {
	feed?: PetActivityFeed;
	now?: () => number;
};

const isRecord = (value: unknown): value is Record<string, unknown> =>
	typeof value === "object" && value !== null && !Array.isArray(value);

const isAbortFailure = (error: Error) =>
	error.name === "AbortError" ||
	error.message === "Fetch is aborted" ||
	error.message === "signal is aborted without reason" ||
	error.message === "component unmounted";

export function createPetActivityAgentSubscriber(
	options: PetActivitySubscriberOptions = {},
): AgentSubscriber {
	const feed = options.feed ?? petActivityFeed;
	const now = options.now ?? Date.now;
	const runCursors = new Map<string, { runId: string; sequence: number }>();

	const acceptRun = (
		input: { runId: string; threadId: string },
		startsRun: boolean,
	) => {
		const cursor = runCursors.get(input.threadId);
		if (!cursor || startsRun) {
			if (!cursor || cursor.runId !== input.runId) {
				runCursors.set(input.threadId, { runId: input.runId, sequence: 0 });
			}
			return true;
		}
		return cursor.runId === input.runId;
	};

	const publishDerived = (
		input: { runId: string; threadId: string },
		event: unknown,
		state: PetServerActivityState | "offline",
		reason?: string,
	) => {
		const cursor = runCursors.get(input.threadId) ?? {
			runId: input.runId,
			sequence: 0,
		};
		const rawSequence =
			isRecord(event) &&
			typeof event.sequence === "number" &&
			Number.isSafeInteger(event.sequence) &&
			event.sequence >= 0
				? event.sequence
				: null;
		cursor.sequence = Math.max(cursor.sequence + 1, rawSequence ?? 0);
		runCursors.set(input.threadId, cursor);
		const atMs = now();
		feed.publish(
			{
				type: PET_ACTIVITY_EVENT_TYPE,
				threadId: input.threadId,
				runId: input.runId,
				sequence: cursor.sequence,
				occurredAt: new Date(atMs).toISOString(),
				state: state === "offline" ? "error" : state,
				...(reason ? { reason } : {}),
			},
			{
				receivedAtMs: atMs,
				source: state === "offline" ? "local-connection" : "ag-ui-derived",
				state,
			},
		);
	};

	const publishContract = (
		input: { runId: string; threadId: string },
		value: unknown,
	) => {
		const activity = parsePetActivityEventV1(value);
		if (
			!activity ||
			activity.threadId !== input.threadId ||
			activity.runId !== input.runId
		) {
			return;
		}
		const cursor = runCursors.get(activity.threadId) ?? {
			runId: activity.runId,
			sequence: 0,
		};
		cursor.sequence = Math.max(cursor.sequence, activity.sequence);
		runCursors.set(activity.threadId, cursor);
		feed.publish(activity, {
			receivedAtMs: now(),
			source: "server-contract",
		});
	};

	return {
		onEvent({ event, input }) {
			if (
				!acceptRun(
					input,
					isRecord(event) && event.type === "RUN_STARTED",
				)
			) {
				return;
			}
			const projection = projectPetActivityFromAgUiEvent(event);
			if (!projection) return;
			if (projection.kind === "contract") {
				publishContract(input, projection.value);
				return;
			}
			publishDerived(input, event, projection.state, projection.reason);
		},
		onRunFailed({ error, input }) {
			if (!acceptRun(input, false)) return;
			publishDerived(
				input,
				{ type: "RUN_FAILED" },
				isAbortFailure(error) ? "idle" : "offline",
				isAbortFailure(error) ? "RUN_CANCELLED" : error.message,
			);
		},
	};
}
