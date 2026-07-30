"use client";

import { useEffect } from "react";

function detectMobilePlatform() {
  const userAgent = navigator.userAgent;
  const isIpadOs =
    navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1;

  if (/iPhone|iPad|iPod/i.test(userAgent) || isIpadOs) return "ios";
  if (/Android/i.test(userAgent)) return "android";
  return navigator.maxTouchPoints > 0 ? "touch" : "web";
}

export function MobileEnvironment() {
  useEffect(() => {
    const root = document.documentElement;
    const viewport = window.visualViewport;
    const virtualKeyboard = (
      navigator as Navigator & {
        virtualKeyboard?: { overlaysContent: boolean };
      }
    ).virtualKeyboard;

    root.dataset.mobilePlatform = detectMobilePlatform();
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
    viewport?.addEventListener("resize", syncViewport);
    viewport?.addEventListener("scroll", syncViewport);

    return () => {
      window.removeEventListener("resize", syncViewport);
      window.removeEventListener("orientationchange", syncViewport);
      viewport?.removeEventListener("resize", syncViewport);
      viewport?.removeEventListener("scroll", syncViewport);
      delete root.dataset.mobilePlatform;
      root.style.removeProperty("--kolibri-visual-viewport-height");
      root.style.removeProperty("--kolibri-visual-viewport-offset-top");
      root.style.removeProperty("--kolibri-keyboard-inset");
    };
  }, []);

  return null;
}
