export const SHELL_ICON_SIZE_CLASS = "size-4";
export const SHELL_ICON_LARGE_SIZE_CLASS = "size-6";
export const SHELL_ICON_STROKE_WIDTH = 1.9;
export const SHELL_ICON_STROKE_THICK = 2.4;
export const SHELL_MOBILE_HEADER_BUTTON_CLASS = "size-12";
export const SHELL_MOBILE_HEADER_GHOST_CLASS = `${SHELL_MOBILE_HEADER_BUTTON_CLASS} rounded-full border border-foreground/45 bg-background p-0 shadow-none hover:bg-muted`;
export const SHELL_DESKTOP_HEADER_ICON_BUTTON_CLASS = "size-7";
export const SHELL_DESKTOP_HEADER_ICON_WRAPPER = "size-4";
export const SHELL_HEADER_ICON_BUTTON_CLASS = `text-muted-foreground hover:text-foreground ${SHELL_DESKTOP_HEADER_ICON_BUTTON_CLASS} rounded-lg`;
export const SHELL_MOBILE_HEADER_TITLE_CLASS =
	"pointer-events-none absolute left-1/2 max-w-[58vw] -translate-x-1/2 truncate text-[21px] leading-none font-semibold tracking-[-0.035em]";
export const SHELL_MOBILE_HEADER_DROPDOWN_BUTTON_CLASS =
	"focus-visible:ring-ring absolute left-1/2 flex h-11 -translate-x-1/2 items-center gap-1 rounded-xl px-2 text-[21px] leading-none font-semibold tracking-[-0.035em] underline decoration-[1.5px] underline-offset-4 outline-none focus-visible:ring-2";

export const PRIMARY_SURFACE_TITLES = {
	chat: "Новая задача",
	projects: "Проекты",
	documents: "Документы",
	references: "Справочники",
} as const;

export const CHAT_DESTINATION_LABEL = "Чат";
export const CHAT_THREAD_FALLBACK_TITLE = "Новая задача";
export type PrimarySurface = keyof typeof PRIMARY_SURFACE_TITLES;

export const CHAT_DESTINATIONS = [
	{ id: "chat", label: CHAT_DESTINATION_LABEL },
	{ id: "projects", label: PRIMARY_SURFACE_TITLES.projects },
	{ id: "documents", label: PRIMARY_SURFACE_TITLES.documents },
	{ id: "references", label: PRIMARY_SURFACE_TITLES.references },
] as const satisfies ReadonlyArray<{ id: PrimarySurface; label: string }>;
