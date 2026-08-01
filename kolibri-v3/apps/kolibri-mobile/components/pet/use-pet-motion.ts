import { useAuiState } from "@assistant-ui/react-native";
import {
	useCallback,
	useEffect,
	useRef,
	useState,
	useSyncExternalStore,
} from "react";

import { haptics } from "@/lib/haptics";
import {
	createPetMotionModel,
	derivePetActivityFromRuntime,
	reducePetMotion,
	type PetActivityState,
	type PetReactionState,
} from "@/src/pets/motion";
import {
	getPetActivitySnapshot,
	getPetMessageAcceptedOrdinal,
	getPetMessageAcceptedSnapshot,
	subscribeToPetActivityFeed,
} from "@/src/pets/runtime-activity";

type ActiveReaction = {
	baseState: PetActivityState;
	state: PetReactionState;
};

function derivePetActivityState(
	thread: Parameters<Parameters<typeof useAuiState>[0]>[0]["thread"],
): PetActivityState {
	const last = thread.messages.at(-1);
	const assistantMessage = last?.role === "assistant" ? last : null;
	const approvalRequired =
		assistantMessage?.parts.some(
			(part) =>
				part.type === "tool-call" &&
				part.approval !== undefined &&
				part.approval.approved === undefined &&
				part.approval.resolution === undefined,
		) ?? false;
	const toolIsRunning =
		assistantMessage?.parts.some(
			(part) =>
				part.type === "tool-call" &&
				part.status.type === "running",
		) ?? false;
	const toolRequiresAction =
		assistantMessage?.parts.some(
			(part) =>
				part.type === "tool-call" && part.status.type === "requires-action",
		) ?? false;
	const lastMessageStatus = !assistantMessage
		? "none"
		: assistantMessage.status.type === "incomplete"
			? assistantMessage.status.reason === "cancelled"
				? "cancelled"
				: "incomplete"
			: assistantMessage.status.type;

	return derivePetActivityFromRuntime({
		approvalRequired,
		isRunning: thread.isRunning,
		lastMessageRole: assistantMessage ? "assistant" : last ? "other" : "none",
		lastMessageStatus,
		toolIsRunning,
		toolRequiresAction,
	});
}

export function usePetMotion() {
	const activeThreadId = useAuiState((state) => state.threads.mainThreadId);
	const runtimeActivity = useAuiState((state) =>
		derivePetActivityState(state.thread),
	);
	const serverActivity = useSyncExternalStore(
		subscribeToPetActivityFeed,
		() => getPetActivitySnapshot(activeThreadId),
		() => null,
	);
	const acceptedMessage = useSyncExternalStore(
		subscribeToPetActivityFeed,
		() => getPetMessageAcceptedSnapshot(activeThreadId),
		() => null,
	);
	const observedActivity = serverActivity?.state ?? runtimeActivity;
	const [activityState, setActivityState] =
		useState<PetActivityState>(() =>
			observedActivity === "success" || observedActivity === "error"
				? "idle"
				: observedActivity,
		);
	const [reaction, setReaction] = useState<ActiveReaction | null>(null);
	const reactionTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
	const completionTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
	const acceptedOrdinalRef = useRef(getPetMessageAcceptedOrdinal());
	const previousObservedRef = useRef<PetActivityState>(observedActivity);
	const previousActivityRef = useRef<PetActivityState>(activityState);

	useEffect(() => {
		const previous = previousObservedRef.current;
		previousObservedRef.current = observedActivity;
		if (completionTimerRef.current) {
			clearTimeout(completionTimerRef.current);
			completionTimerRef.current = null;
		}
		if (observedActivity === "success" || observedActivity === "error") {
			const wasActive =
				previous === "thinking" ||
				previous === "running" ||
				previous === "review" ||
				previous === "waiting" ||
				previous === "approval";
			if (!wasActive) {
				const updateTimer = setTimeout(() => setActivityState("idle"), 0);
				return () => clearTimeout(updateTimer);
			}
			const updateTimer = setTimeout(() => {
				setActivityState(observedActivity);
				completionTimerRef.current = setTimeout(
					() => setActivityState("idle"),
					observedActivity === "success" ? 1_100 : 1_500,
				);
			}, 0);
			return () => clearTimeout(updateTimer);
		}
		const updateTimer = setTimeout(
			() => setActivityState(observedActivity),
			0,
		);
		return () => clearTimeout(updateTimer);
	}, [observedActivity]);

	useEffect(() => {
		const previous = previousActivityRef.current;
		const wasActive =
			previous === "thinking" ||
			previous === "running" ||
			previous === "review" ||
			previous === "waiting" ||
			previous === "approval";
		if (
			wasActive &&
			activityState === "success"
		) {
			haptics.success();
		} else if (wasActive && activityState === "error") {
			haptics.error();
		}
		previousActivityRef.current = activityState;
	}, [activityState]);

	useEffect(
		() => () => {
			if (reactionTimerRef.current) clearTimeout(reactionTimerRef.current);
			if (completionTimerRef.current) clearTimeout(completionTimerRef.current);
		},
		[],
	);

	const startReaction = useCallback(
		(type: "interaction.tap" | "interaction.message-sent") => {
			const now = Date.now();
			const source = {
				...createPetMotionModel(now),
				state: activityState,
				resumeState: activityState,
			};
			const next = reducePetMotion(source, { type, atMs: now });
			if (next.state !== "greeting" && next.state !== "celebrate") return;

			if (reactionTimerRef.current) clearTimeout(reactionTimerRef.current);
			setReaction({ baseState: activityState, state: next.state });
			const duration = Math.max(0, (next.expiresAtMs ?? now) - now);
			reactionTimerRef.current = setTimeout(() => {
				setReaction(null);
				reactionTimerRef.current = null;
			}, duration);
		},
		[activityState],
	);

	useEffect(() => {
		if (
			!acceptedMessage ||
			acceptedMessage.ordinal <= acceptedOrdinalRef.current
		) {
			return;
		}
		acceptedOrdinalRef.current = acceptedMessage.ordinal;
		startReaction("interaction.message-sent");
	}, [acceptedMessage, startReaction]);

	const state =
		reaction?.baseState === activityState ? reaction.state : activityState;

	return {
		activityState,
		onTap: useCallback(
			() => startReaction("interaction.tap"),
			[startReaction],
		),
		state,
	};
}
