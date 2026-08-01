export const KOLIBRI_GENERATIVE_UI_ERROR_MESSAGE =
	"Не удалось показать этот блок. Формат интерфейса не поддерживается.";

export const KOLIBRI_GENERATIVE_UI_STREAMING_MESSAGE =
	"Формирую представление…";

export const CARD_TONE_CLASS = {
	neutral: "bg-card",
	subtle: "bg-muted/45",
	positive: "border-emerald-600/25 bg-emerald-500/[0.045]",
	warning: "border-amber-600/25 bg-amber-500/[0.055]",
} as const;

export const GAP_CLASS = {
	compact: "gap-2",
	regular: "gap-3",
	relaxed: "gap-5",
} as const;

export const ALIGN_CLASS = {
	start: "items-start",
	center: "items-center",
	stretch: "items-stretch",
} as const;

export const GRID_CLASS = {
	1: "grid-cols-1",
	2: "grid-cols-1 sm:grid-cols-2",
	3: "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3",
} as const;

export const TEXT_TONE_CLASS = {
	default: "text-foreground",
	muted: "text-muted-foreground",
	positive: "text-emerald-700 dark:text-emerald-300",
	warning: "text-amber-700 dark:text-amber-300",
} as const;

export const TEXT_SIZE_CLASS = {
	small: "text-xs leading-5",
	regular: "text-sm leading-6",
	large: "text-base leading-7",
} as const;

export const BADGE_TONE_CLASS = {
	neutral: "border-border bg-muted/55 text-muted-foreground",
	positive:
		"border-emerald-600/20 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
	warning:
		"border-amber-600/20 bg-amber-500/10 text-amber-700 dark:text-amber-300",
	critical: "border-destructive/20 bg-destructive/10 text-destructive",
} as const;

export function safeClassName<T extends Record<string | number, string>>(
	values: T,
	requested: unknown,
	fallback: keyof T,
): string {
	if (
		(typeof requested === "string" || typeof requested === "number") &&
		Object.hasOwn(values, requested)
	) {
		return values[requested as keyof T];
	}
	return values[fallback];
}
