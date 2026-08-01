export const PET_ACTIVITY_EVENT_TYPE = "kolibri.pet.activity.v1" as const;

export const PET_ATLAS_LAYOUT = {
	columns: 8,
	rows: 9,
	cellWidth: 192,
	cellHeight: 208,
	width: 1_536,
	height: 1_872,
} as const;

export type PetServerActivityState =
	| "idle"
	| "thinking"
	| "running"
	| "review"
	| "waiting"
	| "approval"
	| "success"
	| "error";

export type PetActivityState = PetServerActivityState | "offline";
export type PetReactionState = "greeting" | "celebrate";
export type PetVisualState = PetActivityState | PetReactionState;

export type PetActivityEventV1 = {
	type: typeof PET_ACTIVITY_EVENT_TYPE;
	threadId: string;
	runId: string;
	sequence: number;
	occurredAt: string;
	state: PetServerActivityState;
	reason?: string;
};

export type PetAgUiActivityProjection =
	| {
			kind: "state";
			state: PetServerActivityState;
			reason: string;
	  }
	| { kind: "contract"; value: unknown };

export type PetAtlasRow =
	| "idle"
	| "running-right"
	| "running-left"
	| "waving"
	| "jumping"
	| "failed"
	| "waiting"
	| "running"
	| "review";

export type PetMotionClip = {
	row: number;
	atlasState: PetAtlasRow;
	frameDurationsMs: readonly number[];
	loop: boolean;
	reducedMotionFrame: number;
};

const RUNNING_CLIP = {
	row: 7,
	atlasState: "running",
	frameDurationsMs: [120, 120, 120, 120, 120, 220],
	loop: true,
	reducedMotionFrame: 2,
} as const satisfies PetMotionClip;

const WAITING_CLIP = {
	row: 6,
	atlasState: "waiting",
	frameDurationsMs: [150, 150, 150, 150, 150, 260],
	loop: true,
	reducedMotionFrame: 2,
} as const satisfies PetMotionClip;

const SUCCESS_CLIP = {
	row: 4,
	atlasState: "jumping",
	frameDurationsMs: [140, 140, 140, 140, 280],
	loop: false,
	reducedMotionFrame: 2,
} as const satisfies PetMotionClip;

const ERROR_CLIP = {
	row: 5,
	atlasState: "failed",
	frameDurationsMs: [140, 140, 140, 140, 140, 140, 140, 240],
	loop: false,
	reducedMotionFrame: 5,
} as const satisfies PetMotionClip;

export const PET_MOTION_CLIPS: Readonly<Record<PetVisualState, PetMotionClip>> = {
	idle: {
		row: 0,
		atlasState: "idle",
		frameDurationsMs: [280, 110, 110, 140, 140, 320],
		loop: true,
		reducedMotionFrame: 0,
	},
	thinking: RUNNING_CLIP,
	running: RUNNING_CLIP,
	review: {
		row: 8,
		atlasState: "review",
		frameDurationsMs: [150, 150, 150, 150, 150, 280],
		loop: true,
		reducedMotionFrame: 2,
	},
	waiting: WAITING_CLIP,
	approval: WAITING_CLIP,
	success: SUCCESS_CLIP,
	error: ERROR_CLIP,
	offline: { ...ERROR_CLIP, loop: false },
	greeting: {
		row: 3,
		atlasState: "waving",
		frameDurationsMs: [140, 140, 140, 280],
		loop: false,
		reducedMotionFrame: 2,
	},
	celebrate: SUCCESS_CLIP,
};

export const PET_ACTIVITY_COPY_RU: Readonly<Record<PetActivityState, string>> = {
	idle: "Готов помочь в этом чате",
	thinking: "Обдумываю ответ…",
	running: "Выполняю задачу…",
	review: "Проверяю результат…",
	waiting: "Жду ваших данных",
	approval: "Нужно ваше подтверждение",
	success: "Ответ готов",
	error: "Не удалось завершить ответ",
	offline: "Связь с агентом недоступна",
};

export type PetServerCursor = {
	threadId: string;
	runId: string;
	sequence: number;
};

export type PetMotionModel = {
	state: PetVisualState;
	resumeState: PetActivityState;
	enteredAtMs: number;
	expiresAtMs: number | null;
	serverCursor: PetServerCursor | null;
};

export type PetMotionEvent =
	| { type: "runtime.idle"; atMs: number }
	| { type: "runtime.thinking"; atMs: number }
	| { type: "runtime.running"; atMs: number }
	| { type: "runtime.review"; atMs: number }
	| { type: "runtime.waiting"; atMs: number }
	| { type: "runtime.approval"; atMs: number }
	| { type: "runtime.success"; atMs: number }
	| { type: "runtime.error"; atMs: number }
	| { type: "runtime.offline"; atMs: number }
	| {
			type: "server.activity";
			atMs: number;
			activeThreadId: string;
			activity: PetActivityEventV1;
	  }
	| { type: "interaction.tap"; atMs: number }
	| { type: "interaction.message-sent"; atMs: number }
	| { type: "time.elapsed"; atMs: number };

export type PetRuntimeObservation = {
	isRunning: boolean;
	lastMessageRole: "assistant" | "other" | "none";
	lastMessageStatus:
		| "running"
		| "requires-action"
		| "complete"
		| "cancelled"
		| "incomplete"
		| "none";
	toolIsRunning: boolean;
	toolRequiresAction: boolean;
	approvalRequired: boolean;
};

const TRANSIENT_DURATION_MS: Readonly<
	Partial<Record<PetVisualState, number>>
> = {
	success: 1_100,
	error: 1_500,
	greeting: 700,
	celebrate: 840,
};

export function createPetMotionModel(atMs = 0): PetMotionModel {
	return {
		state: "idle",
		resumeState: "idle",
		enteredAtMs: atMs,
		expiresAtMs: null,
		serverCursor: null,
	};
}

export function derivePetActivityFromRuntime(
	observation: PetRuntimeObservation,
): PetActivityState {
	if (observation.toolRequiresAction) {
		return observation.approvalRequired ? "approval" : "waiting";
	}
	if (observation.isRunning) {
		return observation.toolIsRunning ? "running" : "thinking";
	}
	if (observation.lastMessageRole !== "assistant") return "idle";
	if (observation.lastMessageStatus === "complete") return "success";
	if (observation.lastMessageStatus === "incomplete") return "error";
	return "idle";
}

function activityModel(
	current: PetMotionModel,
	state: PetActivityState,
	atMs: number,
): PetMotionModel {
	const duration = TRANSIENT_DURATION_MS[state];
	return {
		...current,
		state,
		resumeState: state === "success" || state === "error" ? "idle" : state,
		enteredAtMs: atMs,
		expiresAtMs: duration === undefined ? null : atMs + duration,
	};
}

function reactionModel(
	current: PetMotionModel,
	state: PetReactionState,
	atMs: number,
): PetMotionModel {
	const resumeState =
		current.state === "greeting" || current.state === "celebrate"
			? current.resumeState
			: current.state === "success" || current.state === "error"
				? "idle"
				: current.state;
	return {
		...current,
		state,
		resumeState,
		enteredAtMs: atMs,
		expiresAtMs: atMs + (TRANSIENT_DURATION_MS[state] ?? 0),
	};
}

function isNewerServerActivity(
	current: PetMotionModel,
	activeThreadId: string,
	activity: PetActivityEventV1,
): boolean {
	if (activity.threadId !== activeThreadId) return false;
	const cursor = current.serverCursor;
	if (!cursor) return true;
	if (cursor.threadId !== activity.threadId || cursor.runId !== activity.runId) {
		return true;
	}
	return activity.sequence > cursor.sequence;
}

export function reducePetMotion(
	current: PetMotionModel,
	event: PetMotionEvent,
): PetMotionModel {
	switch (event.type) {
		case "runtime.idle":
			return activityModel(current, "idle", event.atMs);
		case "runtime.thinking":
			return activityModel(current, "thinking", event.atMs);
		case "runtime.running":
			return activityModel(current, "running", event.atMs);
		case "runtime.review":
			return activityModel(current, "review", event.atMs);
		case "runtime.waiting":
			return activityModel(current, "waiting", event.atMs);
		case "runtime.approval":
			return activityModel(current, "approval", event.atMs);
		case "runtime.success":
			return activityModel(current, "success", event.atMs);
		case "runtime.error":
			return activityModel(current, "error", event.atMs);
		case "runtime.offline":
			return activityModel(current, "offline", event.atMs);
		case "server.activity": {
			if (
				!isNewerServerActivity(
					current,
					event.activeThreadId,
					event.activity,
				)
			) {
				return current;
			}
			const next = activityModel(current, event.activity.state, event.atMs);
			return {
				...next,
				serverCursor: {
					threadId: event.activity.threadId,
					runId: event.activity.runId,
					sequence: event.activity.sequence,
				},
			};
		}
		case "interaction.tap":
			return reactionModel(current, "greeting", event.atMs);
		case "interaction.message-sent":
			return reactionModel(current, "celebrate", event.atMs);
		case "time.elapsed":
			if (current.expiresAtMs === null || event.atMs < current.expiresAtMs) {
				return current;
			}
			return activityModel(current, current.resumeState, event.atMs);
	}
}

function isRecord(value: unknown): value is Record<string, unknown> {
	return typeof value === "object" && value !== null && !Array.isArray(value);
}

function projectRunFinishedState(
	event: Record<string, unknown>,
): PetServerActivityState {
	const outcome = isRecord(event.outcome) ? event.outcome : null;
	if (outcome?.type !== "interrupt" || !Array.isArray(outcome.interrupts)) {
		return "success";
	}
	return outcome.interrupts.some(
		(interrupt) =>
			isRecord(interrupt) &&
			(interrupt.reason === "confirmation" || interrupt.reason === "tool_call"),
	)
		? "approval"
		: "waiting";
}

/**
 * Turns provider-neutral AG-UI lifecycle events into the portable pet model.
 * A backend-emitted `kolibri.pet.activity.v1` contract remains authoritative;
 * the standard lifecycle mapping is only the truthful compatibility bridge.
 */
export function projectPetActivityFromAgUiEvent(
	event: unknown,
): PetAgUiActivityProjection | null {
	if (!isRecord(event) || typeof event.type !== "string") return null;
	switch (event.type) {
		case "RUN_STARTED":
		case "THINKING_START":
		case "REASONING_START":
			return { kind: "state", state: "thinking", reason: event.type };
		case "STEP_STARTED":
		case "TOOL_CALL_START":
			return { kind: "state", state: "running", reason: event.type };
		case "STEP_FINISHED":
		case "TOOL_CALL_RESULT":
		case "TEXT_MESSAGE_START":
			return { kind: "state", state: "review", reason: event.type };
		case "RUN_FINISHED":
			return {
				kind: "state",
				state: projectRunFinishedState(event),
				reason: event.type,
			};
		case "RUN_ERROR":
			return {
				kind: "state",
				state: "error",
				reason:
					typeof event.message === "string" ? event.message : event.type,
			};
		case "CUSTOM":
			return event.name === PET_ACTIVITY_EVENT_TYPE
				? { kind: "contract", value: event.value }
				: null;
		case "ACTIVITY_SNAPSHOT":
			return event.activityType === PET_ACTIVITY_EVENT_TYPE
				? { kind: "contract", value: event.content }
				: null;
		default:
			return null;
	}
}

export function parsePetActivityEventV1(
	value: unknown,
): PetActivityEventV1 | null {
	if (!isRecord(value) || value.type !== PET_ACTIVITY_EVENT_TYPE) return null;
	if (
		typeof value.threadId !== "string" ||
		value.threadId.length === 0 ||
		typeof value.runId !== "string" ||
		value.runId.length === 0 ||
		typeof value.sequence !== "number" ||
		!Number.isSafeInteger(value.sequence) ||
		value.sequence < 0 ||
		typeof value.occurredAt !== "string" ||
		Number.isNaN(Date.parse(value.occurredAt)) ||
		!isPetServerActivityState(value.state) ||
		(value.reason !== undefined && typeof value.reason !== "string")
	) {
		return null;
	}
	return {
		type: PET_ACTIVITY_EVENT_TYPE,
		threadId: value.threadId,
		runId: value.runId,
		sequence: value.sequence,
		occurredAt: value.occurredAt,
		state: value.state,
		...(value.reason === undefined ? {} : { reason: value.reason }),
	};
}

export function isPetServerActivityState(
	value: unknown,
): value is PetServerActivityState {
	return (
		value === "idle" ||
		value === "thinking" ||
		value === "running" ||
		value === "review" ||
		value === "waiting" ||
		value === "approval" ||
		value === "success" ||
		value === "error"
	);
}

export function getPetClipDurationMs(clip: PetMotionClip): number {
	return clip.frameDurationsMs.reduce((total, duration) => total + duration, 0);
}

export function getPetFrameAtElapsedMs(
	clip: PetMotionClip,
	elapsedMs: number,
	reducedMotion = false,
): number {
	if (reducedMotion) return clip.reducedMotionFrame;
	if (elapsedMs <= 0) return 0;

	const duration = getPetClipDurationMs(clip);
	const boundedElapsed = clip.loop
		? elapsedMs % duration
		: Math.min(elapsedMs, Math.max(0, duration - 1));
	let cursor = 0;
	for (let index = 0; index < clip.frameDurationsMs.length; index += 1) {
		cursor += clip.frameDurationsMs[index] ?? 0;
		if (boundedElapsed < cursor) return index;
	}
	return clip.frameDurationsMs.length - 1;
}
