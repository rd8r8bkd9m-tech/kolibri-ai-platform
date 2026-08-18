"use client";

import { useEffect, useState } from "react";

// Spec: docs/design/desktop-mobile-redesign-spec.md §5. Docked 3-pane layout
// is allowed only when the viewport fits nav + chat + auxiliary at their
// minimums; otherwise navigation becomes an overlay first, then auxiliary
// goes fullscreen. The chat canvas must never shrink below 640 px.
const NAVIGATION_MIN_WIDTH = 280;
const CHAT_MIN_WIDTH = 640;
const AUXILIARY_MIN_WIDTH = 320;

const DOCKED_NAVIGATION_WITH_AUXILIARY_MIN =
	NAVIGATION_MIN_WIDTH + CHAT_MIN_WIDTH + AUXILIARY_MIN_WIDTH;
const DOCKED_NAVIGATION_MIN = NAVIGATION_MIN_WIDTH + CHAT_MIN_WIDTH;
const DOCKED_AUXILIARY_MIN = CHAT_MIN_WIDTH + AUXILIARY_MIN_WIDTH;

export type AdaptiveWorkspaceLayout = {
	auxiliaryDocked: boolean;
	navigationOverlay: boolean;
	viewportWidth: number;
};

export function useAdaptiveWorkspaceLayout({
	auxiliaryOpen,
	navigationOpen,
}: {
	auxiliaryOpen: boolean;
	navigationOpen: boolean;
}): AdaptiveWorkspaceLayout {
	const [viewportWidth, setViewportWidth] = useState<number | null>(null);

	useEffect(() => {
		const syncWidth = () => setViewportWidth(window.innerWidth);
		syncWidth();
		window.addEventListener("resize", syncWidth);
		return () => window.removeEventListener("resize", syncWidth);
	}, []);

	// Before the first client measurement keep the docked desktop layout to
	// avoid a hydration mismatch; the resize listener corrects it immediately.
	const width = viewportWidth;

	const auxiliaryDocked = auxiliaryOpen && (width === null || width >= DOCKED_AUXILIARY_MIN);
	const navigationOverlay =
		navigationOpen &&
		width !== null &&
		width <
			(auxiliaryDocked
				? DOCKED_NAVIGATION_WITH_AUXILIARY_MIN
				: DOCKED_NAVIGATION_MIN);

	return {
		auxiliaryDocked,
		navigationOverlay,
		viewportWidth: width ?? Number.POSITIVE_INFINITY,
	};
}
