"use client";

import { useEffect, useState } from "react";

const DESKTOP_APP_PATH = /^\/app(?:\/|$)/;
const MOBILE_BREAKPOINT_QUERY = "(max-width: 959px)";

function mobileAppUrl() {
	const url = new URL(window.location.href);
	// The gateway keeps both clients on the same public origin and uses this
	// explicit selector only for a viewport handoff from desktop Next to Expo.
	url.searchParams.set("client", "mobile");
	return url.toString();
}

function hasUiGatewayAffinity() {
	return document.cookie
		.split(";")
		.some((cookie) => cookie.trim().startsWith("kolibri_ui_client="));
}

function detectMobilePlatform() {
	const userAgent = navigator.userAgent;
	const isIpadOs =
		navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1;

	if (/iPhone|iPad|iPod/i.test(userAgent) || isIpadOs) return "ios";
	if (/Android/i.test(userAgent)) return "android";
	return navigator.maxTouchPoints > 0 ? "touch" : "web";
}

export function MobileEnvironment() {
	const [handoff, setHandoff] = useState(false);

	useEffect(() => {
		const root = document.documentElement;
		const viewport = window.visualViewport;
		const virtualKeyboard = (
			navigator as Navigator & {
				virtualKeyboard?: { overlaysContent: boolean };
			}
		).virtualKeyboard;

		const mobileViewport = window.matchMedia(MOBILE_BREAKPOINT_QUERY);
		let handoffScheduled = false;
		const handoffToMobileWeb = () => {
			if (
				handoffScheduled ||
				!hasUiGatewayAffinity() ||
				!DESKTOP_APP_PATH.test(window.location.pathname)
			) {
				return;
			}
			handoffScheduled = true;
			setHandoff(true);
			window.location.replace(mobileAppUrl());
		};

		root.dataset.mobilePlatform = detectMobilePlatform();
		if (mobileViewport.matches) handoffToMobileWeb();
		try {
			if (virtualKeyboard) virtualKeyboard.overlaysContent = false;
		} catch {
			// Browsers may expose the API without allowing policy changes.
		}

		const syncViewport = () => {
			const visibleHeight = viewport?.height ?? window.innerHeight;
			const visibleOffset = viewport?.offsetTop ?? 0;
			const keyboardInset = Math.max(
				0,
				window.innerHeight - visibleHeight - visibleOffset,
			);

			root.style.setProperty(
				"--kolibri-visual-viewport-height",
				`${Math.round(visibleHeight)}px`,
			);
			root.style.setProperty(
				"--kolibri-visual-viewport-offset-top",
				`${Math.round(visibleOffset)}px`,
			);
			root.style.setProperty(
				"--kolibri-keyboard-inset",
				`${Math.round(keyboardInset)}px`,
			);
		};

		syncViewport();
		window.addEventListener("resize", syncViewport);
		window.addEventListener("orientationchange", syncViewport);
		mobileViewport.addEventListener("change", handoffToMobileWeb);
		viewport?.addEventListener("resize", syncViewport);
		viewport?.addEventListener("scroll", syncViewport);

		return () => {
			window.removeEventListener("resize", syncViewport);
			window.removeEventListener("orientationchange", syncViewport);
			mobileViewport.removeEventListener("change", handoffToMobileWeb);
			viewport?.removeEventListener("resize", syncViewport);
			viewport?.removeEventListener("scroll", syncViewport);
			delete root.dataset.mobilePlatform;
			root.style.removeProperty("--kolibri-visual-viewport-height");
			root.style.removeProperty("--kolibri-visual-viewport-offset-top");
			root.style.removeProperty("--kolibri-keyboard-inset");
		};
	}, []);

	if (!handoff) return null;
	return (
		<div
			aria-live="polite"
			style={{
				alignItems: "center",
				background: "var(--background, #fff)",
				color: "var(--foreground, #111)",
				display: "flex",
				fontFamily: "system-ui, sans-serif",
				fontSize: 14,
				inset: 0,
				justifyContent: "center",
				position: "fixed",
				zIndex: 2147483647,
			}}
		>
			Открываем мобильную версию…
		</div>
	);
}
