import {
	EMPTY_CANVAS_SCOPE,
	getActiveCanvasView,
	isCanvasVisible,
	normalizeCanvasId,
	normalizeCanvasScope,
	normalizeCanvasTitle,
	normalizeCanvasView,
	type CanvasPresentation,
	type CanvasScope,
	type CanvasSlot,
	type CanvasView,
	type OpenWorkspaceCanvasInput,
	type WorkspaceCanvas,
	type WorkspaceCanvasState,
} from "./model";

export type WorkspaceCanvasAction =
	| { type: "canvas/open"; canvas: OpenWorkspaceCanvasInput }
	| { type: "canvas/close"; canvasId: string }
	| { type: "canvas/focus"; canvasId: string }
	| {
			type: "canvas/presentation";
			canvasId: string;
			presentation: CanvasPresentation;
	  }
	| { type: "canvas/slot"; canvasId: string; slot: CanvasSlot }
	| { type: "canvas/scope"; canvasId: string; scope: Partial<CanvasScope> }
	| { type: "view/open"; canvasId: string; view: CanvasView }
	| { type: "view/close"; canvasId: string; viewId: string }
	| { type: "view/select"; canvasId: string; viewId: string };

export function createWorkspaceCanvasState(
	canvases: readonly WorkspaceCanvas[] = [],
	focusedCanvasId: string | null = null,
): WorkspaceCanvasState {
	let state: WorkspaceCanvasState = {
		canvasOrder: [],
		canvases: {},
		focusedCanvasId: null,
		version: 1,
	};

	for (const canvas of canvases) {
		state = openWorkspaceCanvas(state, {
			id: canvas.id,
			presentation: canvas.presentation,
			role: canvas.role,
			scope: canvas.scope,
			slot: canvas.slot,
			title: canvas.title,
		});
		for (const view of canvas.views) {
			state = openCanvasView(state, canvas.id, view);
		}
		if (canvas.activeViewId) {
			state = selectCanvasView(state, canvas.id, canvas.activeViewId);
		}
	}

	return focusWorkspaceCanvas(state, focusedCanvasId ?? state.focusedCanvasId ?? "");
}

export function createPrimaryChatCanvas({
	canvasId = "canvas:primary",
	projectId = null,
	threadId = null,
	title = "Чат",
}: {
	canvasId?: string;
	projectId?: string | null;
	threadId?: string | null;
	title?: string;
} = {}): WorkspaceCanvas {
	const view: CanvasView = {
		id: threadId ? `thread:${threadId}` : "thread:new",
		surface: { kind: "chat", projectId, threadId },
		title,
	};
	return {
		activeViewId: view.id,
		id: normalizeCanvasId(canvasId) || "canvas:primary",
		presentation: "docked",
		role: "primary",
		scope: {
			...EMPTY_CANVAS_SCOPE,
			linkMode: projectId ? "project" : "isolated",
			projectId,
		},
		slot: "primary",
		title: normalizeCanvasTitle(title),
		views: [view],
	};
}

export function workspaceCanvasReducer(
	state: WorkspaceCanvasState,
	action: WorkspaceCanvasAction,
): WorkspaceCanvasState {
	switch (action.type) {
		case "canvas/open":
			return openWorkspaceCanvas(state, action.canvas);
		case "canvas/close":
			return closeWorkspaceCanvas(state, action.canvasId);
		case "canvas/focus":
			return focusWorkspaceCanvas(state, action.canvasId);
		case "canvas/presentation":
			return setWorkspaceCanvasPresentation(
				state,
				action.canvasId,
				action.presentation,
			);
		case "canvas/slot":
			return updateWorkspaceCanvas(state, action.canvasId, (canvas) =>
				canvas.role === "primary" ? canvas : { ...canvas, slot: action.slot },
			);
		case "canvas/scope":
			return updateWorkspaceCanvas(state, action.canvasId, (canvas) => ({
				...canvas,
				scope: normalizeCanvasScope({ ...canvas.scope, ...action.scope }),
			}));
		case "view/open":
			return openCanvasView(state, action.canvasId, action.view);
		case "view/close":
			return closeCanvasView(state, action.canvasId, action.viewId);
		case "view/select":
			return selectCanvasView(state, action.canvasId, action.viewId);
	}
}

export function openWorkspaceCanvas(
	state: WorkspaceCanvasState,
	input: OpenWorkspaceCanvasInput,
): WorkspaceCanvasState {
	const id = normalizeCanvasId(input.id);
	if (!id) return state;
	const existing = state.canvases[id];
	const role = existing?.role ?? input.role ?? "auxiliary";
	const next: WorkspaceCanvas = {
		activeViewId: existing?.activeViewId ?? null,
		id,
		presentation:
			input.presentation ?? existing?.presentation ?? "docked",
		role,
		scope: normalizeCanvasScope({ ...existing?.scope, ...input.scope }),
		slot: role === "primary" ? "primary" : (input.slot ?? existing?.slot ?? "right"),
		title: normalizeCanvasTitle(input.title || existing?.title || ""),
		views: existing?.views ?? [],
	};
	const withCanvas: WorkspaceCanvasState = {
		...state,
		canvasOrder: existing ? state.canvasOrder : [...state.canvasOrder, id],
		canvases: { ...state.canvases, [id]: next },
		focusedCanvasId: id,
	};
	return input.view ? openCanvasView(withCanvas, id, input.view) : withCanvas;
}

export function closeWorkspaceCanvas(
	state: WorkspaceCanvasState,
	canvasId: string,
): WorkspaceCanvasState {
	const id = normalizeCanvasId(canvasId);
	const target = state.canvases[id];
	if (!target || target.role === "primary") return state;
	const canvases = { ...state.canvases };
	delete canvases[id];
	const canvasOrder = state.canvasOrder.filter((candidate) => candidate !== id);
	return {
		...state,
		canvasOrder,
		canvases,
		focusedCanvasId:
			state.focusedCanvasId === id
				? lastVisibleCanvasId(canvasOrder, canvases)
				: state.focusedCanvasId,
	};
}

export function focusWorkspaceCanvas(
	state: WorkspaceCanvasState,
	canvasId: string,
): WorkspaceCanvasState {
	const id = normalizeCanvasId(canvasId);
	const canvas = state.canvases[id];
	if (!canvas || !isCanvasVisible(canvas)) return state;
	return state.focusedCanvasId === id
		? state
		: { ...state, focusedCanvasId: id };
}

export function setWorkspaceCanvasPresentation(
	state: WorkspaceCanvasState,
	canvasId: string,
	presentation: CanvasPresentation,
): WorkspaceCanvasState {
	const id = normalizeCanvasId(canvasId);
	const target = state.canvases[id];
	if (!target) return state;
	if (target.role === "primary" && presentation === "minimized") return state;

	const canvases = { ...state.canvases };
	if (presentation === "fullscreen") {
		for (const [candidateId, canvas] of Object.entries(canvases)) {
			if (candidateId !== id && canvas.presentation === "fullscreen") {
				canvases[candidateId] = { ...canvas, presentation: "expanded" };
			}
		}
	}
	canvases[id] = { ...target, presentation };

	return {
		...state,
		canvases,
		focusedCanvasId:
			presentation === "minimized"
				? lastVisibleCanvasId(state.canvasOrder, canvases)
				: id,
	};
}

export function openCanvasView(
	state: WorkspaceCanvasState,
	canvasId: string,
	view: CanvasView,
): WorkspaceCanvasState {
	const normalizedView = normalizeCanvasView(view);
	if (!normalizedView) return state;
	return updateWorkspaceCanvas(state, canvasId, (canvas) => {
		const index = canvas.views.findIndex(
			(candidate) => candidate.id === normalizedView.id,
		);
		const views = [...canvas.views];
		if (index < 0) views.push(normalizedView);
		else views[index] = normalizedView;
		return {
			...canvas,
			activeViewId: normalizedView.id,
			presentation:
				canvas.presentation === "minimized" ? "docked" : canvas.presentation,
			views,
		};
	});
}

export function closeCanvasView(
	state: WorkspaceCanvasState,
	canvasId: string,
	viewId: string,
): WorkspaceCanvasState {
	const id = normalizeCanvasId(viewId);
	return updateWorkspaceCanvas(state, canvasId, (canvas) => {
		if (!canvas.views.some((view) => view.id === id)) return canvas;
		if (canvas.role === "primary" && canvas.views.length === 1) return canvas;
		const index = canvas.views.findIndex((view) => view.id === id);
		const views = canvas.views.filter((view) => view.id !== id);
		const fallback = views[Math.min(index, views.length - 1)] ?? null;
		return {
			...canvas,
			activeViewId:
				canvas.activeViewId === id
					? fallback?.id ?? null
					: canvas.activeViewId,
			views,
		};
	});
}

export function selectCanvasView(
	state: WorkspaceCanvasState,
	canvasId: string,
	viewId: string,
): WorkspaceCanvasState {
	const id = normalizeCanvasId(viewId);
	return updateWorkspaceCanvas(state, canvasId, (canvas) =>
		canvas.views.some((view) => view.id === id)
			? { ...canvas, activeViewId: id }
			: canvas,
	);
}

export function getFocusedWorkspaceCanvas(state: WorkspaceCanvasState) {
	return state.focusedCanvasId
		? (state.canvases[state.focusedCanvasId] ?? null)
		: null;
}

export function getVisibleWorkspaceCanvases(state: WorkspaceCanvasState) {
	return state.canvasOrder
		.map((id) => state.canvases[id])
		.filter(
			(canvas): canvas is WorkspaceCanvas =>
				canvas !== undefined && isCanvasVisible(canvas),
		);
}

export function getWorkspaceCanvasActiveSurface(
	state: WorkspaceCanvasState,
	canvasId: string,
) {
	const canvas = state.canvases[normalizeCanvasId(canvasId)];
	return canvas ? getActiveCanvasView(canvas)?.surface ?? null : null;
}

function updateWorkspaceCanvas(
	state: WorkspaceCanvasState,
	canvasId: string,
	update: (canvas: WorkspaceCanvas) => WorkspaceCanvas,
): WorkspaceCanvasState {
	const id = normalizeCanvasId(canvasId);
	const canvas = state.canvases[id];
	if (!canvas) return state;
	const next = update(canvas);
	if (next === canvas) return state;
	return {
		...state,
		canvases: { ...state.canvases, [id]: next },
		focusedCanvasId:
			next.presentation === "minimized" && state.focusedCanvasId === id
				? lastVisibleCanvasId(state.canvasOrder, {
						...state.canvases,
						[id]: next,
					})
				: id,
	};
}

function lastVisibleCanvasId(
	order: readonly string[],
	canvases: Readonly<Record<string, WorkspaceCanvas>>,
) {
	for (let index = order.length - 1; index >= 0; index -= 1) {
		const id = order[index];
		const canvas = canvases[id];
		if (canvas && isCanvasVisible(canvas)) return id;
	}
	return null;
}
