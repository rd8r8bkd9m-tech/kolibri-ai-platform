export const CANVAS_SLOTS = ["primary", "right", "bottom", "floating"] as const;
export const CANVAS_PRESENTATIONS = [
	"docked",
	"expanded",
	"fullscreen",
	"minimized",
] as const;
export const BUILTIN_CANVAS_SURFACES = [
	"chat",
	"files",
	"projects",
	"document",
	"browser",
	"marketplace",
	"review",
	"terminal",
	"references",
] as const;

export type CanvasSlot = (typeof CANVAS_SLOTS)[number];
export type CanvasPresentation = (typeof CANVAS_PRESENTATIONS)[number];
export type BuiltinCanvasSurface = (typeof BUILTIN_CANVAS_SURFACES)[number];
export type CanvasSurfaceKind = BuiltinCanvasSurface | (string & {});
export type CanvasRole = "primary" | "auxiliary";
export type CanvasLinkMode = "isolated" | "project" | "orchestrated";

export type CanvasJsonValue =
	| boolean
	| number
	| string
	| null
	| readonly CanvasJsonValue[]
	| { readonly [key: string]: CanvasJsonValue };

/**
 * A surface is a reference to product state, not a copy of that state.
 * Document, project and thread authorities remain on the V3 backend.
 */
export type CanvasSurfaceDescriptor = {
	kind: CanvasSurfaceKind;
	parameters?: Readonly<Record<string, CanvasJsonValue>>;
	projectId?: string | null;
	resourceId?: string | null;
	threadId?: string | null;
};

export type CanvasView = {
	id: string;
	surface: CanvasSurfaceDescriptor;
	title: string;
};

/**
 * Defines how an auxiliary canvas participates in a coordinated workspace.
 * `orchestrationId` is an opaque backend-owned channel identifier; it is not a
 * second source of truth for thread or project data.
 */
export type CanvasScope = {
	linkMode: CanvasLinkMode;
	orchestrationId: string | null;
	parentCanvasId: string | null;
	projectId: string | null;
};

export type WorkspaceCanvas = {
	activeViewId: string | null;
	id: string;
	presentation: CanvasPresentation;
	role: CanvasRole;
	scope: CanvasScope;
	slot: CanvasSlot;
	title: string;
	views: readonly CanvasView[];
};

export type WorkspaceCanvasState = {
	canvasOrder: readonly string[];
	canvases: Readonly<Record<string, WorkspaceCanvas>>;
	focusedCanvasId: string | null;
	version: 1;
};

export type OpenWorkspaceCanvasInput = {
	id: string;
	presentation?: CanvasPresentation;
	role?: CanvasRole;
	scope?: Partial<CanvasScope>;
	slot?: CanvasSlot;
	title: string;
	view?: CanvasView;
};

export const EMPTY_CANVAS_SCOPE: CanvasScope = Object.freeze({
	linkMode: "isolated",
	orchestrationId: null,
	parentCanvasId: null,
	projectId: null,
});

export function normalizeCanvasId(value: string) {
	return value.trim();
}

export function normalizeCanvasTitle(value: string) {
	return value.trim() || "Рабочая область";
}

export function normalizeCanvasView(view: CanvasView): CanvasView | null {
	const id = normalizeCanvasId(view.id);
	if (!id) return null;
	return {
		...view,
		id,
		title: normalizeCanvasTitle(view.title),
	};
}

export function normalizeCanvasScope(
	scope: Partial<CanvasScope> | undefined,
): CanvasScope {
	return {
		linkMode: scope?.linkMode ?? EMPTY_CANVAS_SCOPE.linkMode,
		orchestrationId: scope?.orchestrationId?.trim() || null,
		parentCanvasId: scope?.parentCanvasId?.trim() || null,
		projectId: scope?.projectId?.trim() || null,
	};
}

export function getActiveCanvasView(canvas: WorkspaceCanvas) {
	return (
		canvas.views.find((view) => view.id === canvas.activeViewId) ??
		canvas.views[0] ??
		null
	);
}

export function isCanvasVisible(canvas: WorkspaceCanvas) {
	return canvas.presentation !== "minimized";
}
