"use client";

import { useAuiState } from "@assistant-ui/react";
import { useCallback, useEffect, useRef, useState } from "react";
import {
	createPetMotionModel,
	derivePetActivityFromRuntime,
	reducePetMotion,
	type PetActivityState,
	type PetReactionState,
} from "@/lib/pets/motion";

type ActiveReaction = {
	baseState: PetActivityState;
	state: PetReactionState;
};

export function useWebPetMotion() {
	const observedActivity = useAuiState((state) => {
		const last = state.thread.messages.at(-1);
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
					part.type === "tool-call" &&
					part.status.type === "requires-action",
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
			isRunning: state.thread.isRunning,
			lastMessageRole: assistantMessage ? "assistant" : last ? "other" : "none",
			lastMessageStatus,
			toolIsRunning,
			toolRequiresAction,
		});
	});
	const [activityState, setActivityState] =
		useState<PetActivityState>(() =>
			observedActivity === "success" || observedActivity === "error"
				? "idle"
				: observedActivity,
		);
	const [reaction, setReaction] = useState<ActiveReaction | null>(null);
	const reactionTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
	const completionTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
	const previousObservedRef = useRef<PetActivityState>(observedActivity);

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
			reactionTimerRef.current = setTimeout(() => {
				setReaction(null);
				reactionTimerRef.current = null;
			}, Math.max(0, (next.expiresAtMs ?? now) - now));
		},
		[activityState],
	);

	return {
		activityState,
		onMessageSent: useCallback(
			() => startReaction("interaction.message-sent"),
			[startReaction],
		),
		onTap: useCallback(
			() => startReaction("interaction.tap"),
			[startReaction],
		),
		state:
			reaction?.baseState === activityState ? reaction.state : activityState,
	};
}
