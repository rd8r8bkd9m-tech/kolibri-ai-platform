export const DESKTOP_ENTER_WIDTH = 960;
export const DESKTOP_EXIT_WIDTH = 860;
const DESKTOP_MEDIA_QUERY = `(min-width: ${DESKTOP_ENTER_WIDTH}px)`;

export function resolveDesktopWorkspaceState(
	viewportWidth: number,
	previousState: boolean,
) {
	return previousState ? viewportWidth >= DESKTOP_EXIT_WIDTH : viewportWidth >= DESKTOP_ENTER_WIDTH;
}

export function initialDesktopWorkspaceState() {
	if (typeof window === "undefined") {
		return true;
	}
	if (typeof window.matchMedia === "function") {
		return window.matchMedia(DESKTOP_MEDIA_QUERY).matches;
	}
	return resolveDesktopWorkspaceState(window.innerWidth, true);
}

export function getWindowWidthSafe() {
	return window.innerWidth;
}
