import type { CanvasSurfaceKind } from "./model";

export type CanvasSurfaceCapabilities = {
	canFullscreen: boolean;
	canOpenMultiple: boolean;
	canResize: boolean;
	requiresProject: boolean;
};

export type CanvasSurfaceDefinition<TPayload = unknown> = {
	capabilities: CanvasSurfaceCapabilities;
	id: CanvasSurfaceKind;
	label: string;
	payload: TPayload;
};

export type CanvasSurfaceRegistry<TPayload = unknown> = {
	definitions: readonly CanvasSurfaceDefinition<TPayload>[];
	get: (id: CanvasSurfaceKind) => CanvasSurfaceDefinition<TPayload> | null;
	has: (id: CanvasSurfaceKind) => boolean;
};

/**
 * Creates an immutable lookup used by launchers and renderers alike. Adding a
 * surface therefore registers one definition instead of wiring a button to a
 * page in WorkspaceShell.
 */
export function createCanvasSurfaceRegistry<TPayload>(
	definitions: readonly CanvasSurfaceDefinition<TPayload>[],
): CanvasSurfaceRegistry<TPayload> {
	const byId = new Map<CanvasSurfaceKind, CanvasSurfaceDefinition<TPayload>>();
	for (const definition of definitions) {
		if (byId.has(definition.id)) {
			throw new Error(`Duplicate canvas surface: ${definition.id}`);
		}
		byId.set(definition.id, Object.freeze({ ...definition }));
	}
	const frozenDefinitions = Object.freeze([...byId.values()]);
	return Object.freeze({
		definitions: frozenDefinitions,
		get: (id: CanvasSurfaceKind) => byId.get(id) ?? null,
		has: (id: CanvasSurfaceKind) => byId.has(id),
	});
}

export const DEFAULT_CANVAS_CAPABILITIES: CanvasSurfaceCapabilities =
	Object.freeze({
		canFullscreen: true,
		canOpenMultiple: true,
		canResize: true,
		requiresProject: false,
	});
