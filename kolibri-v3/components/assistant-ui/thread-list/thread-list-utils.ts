import {
	canStartThreadLongPress,
	shouldIgnoreThreadMenuCloseRequest,
	THREAD_LONG_PRESS_CLICK_SUPPRESSION_MS,
	THREAD_LONG_PRESS_DURATION_MS,
	THREAD_LONG_PRESS_MOVE_TOLERANCE_PX,
} from "@/lib/mobile-thread-navigation";

export const DAY_IN_MS = 86_400_000;
export const COMPACT_THREAD_MENU_QUERY = "(max-width: 959px)";

export type ThreadListItemLike = {
	id: string;
	title?: string;
	custom?: {
		pinned?: boolean;
	};
	lastMessageAt?: Date | null;
};

export const DEFAULT_THREAD_TITLE = "Новая задача";

export function normalizeThreadListSearchQuery(value: string) {
	return value.trim().toLowerCase();
}

export function buildThreadItemByIdMap<T extends { id: string }>(items: readonly T[]) {
	return new Map(items.map((item) => [item.id, item]));
}

export function threadItemMatchesQuery(
	title: string | undefined,
	query: string,
	fallbackTitle = DEFAULT_THREAD_TITLE,
) {
	return !query || (title ?? fallbackTitle).toLowerCase().includes(query);
}

export function getThreadDateGroupLabel(
	date: Date | null | undefined,
	startOfToday: number,
) {
	if (!date || date.getTime() >= startOfToday) return "Сегодня";
	if (date.getTime() >= startOfToday - DAY_IN_MS) return "Вчера";
	return "Ранее";
}

export function getThreadItemIndicesByQuery<T extends ThreadListItemLike>(
	ids: readonly string[],
	items: readonly T[],
	query: string,
) {
	const normalizedQuery = normalizeThreadListSearchQuery(query);
	const itemById = buildThreadItemByIdMap(items);
	return ids
		.map((id, index) => ({ id, index }))
		.filter(({ id }) =>
			threadItemMatchesQuery(
				itemById.get(id)?.title,
				normalizedQuery,
				DEFAULT_THREAD_TITLE,
			),
		)
		.map(({ index }) => index);
}

export function subscribeCompactThreadMenu(listener: () => void) {
	const media = window.matchMedia(COMPACT_THREAD_MENU_QUERY);
	media.addEventListener("change", listener);
	return () => media.removeEventListener("change", listener);
}

export function compactThreadMenuSnapshot() {
	return window.matchMedia(COMPACT_THREAD_MENU_QUERY).matches;
}

export function serverCompactThreadMenuSnapshot() {
	return false;
}

export {
	canStartThreadLongPress,
	shouldIgnoreThreadMenuCloseRequest,
	THREAD_LONG_PRESS_CLICK_SUPPRESSION_MS,
	THREAD_LONG_PRESS_DURATION_MS,
	THREAD_LONG_PRESS_MOVE_TOLERANCE_PX,
};
