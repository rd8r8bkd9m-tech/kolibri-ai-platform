import { useLayoutEffect } from "react";

export function resolveShellViewportHeight(visualHeight, innerHeight) {
  const preferred = Number(visualHeight);
  if (Number.isFinite(preferred) && preferred > 0) return Math.floor(preferred);
  const fallback = Number(innerHeight);
  return Number.isFinite(fallback) && fallback > 0 ? Math.floor(fallback) : null;
}

export function resolveShellViewportOffset(visualOffsetTop) {
  const offset = Number(visualOffsetTop);
  return Number.isFinite(offset) && offset > 0 ? Math.floor(offset) : 0;
}

export function useShellViewport(rootRef) {
  useLayoutEffect(() => {
    const viewport = globalThis.visualViewport;
    let frame = 0;
    const measure = () => {
      frame = 0;
      const height = resolveShellViewportHeight(viewport?.height, globalThis.innerHeight);
      const offsetTop = resolveShellViewportOffset(viewport?.offsetTop);
      const root = rootRef.current;
      if (root?.isConnected && height) {
        root.style.setProperty("--shell-viewport-height", `${height}px`);
        root.style.setProperty("--shell-viewport-offset-top", `${offsetTop}px`);
      }
    };
    const schedule = () => {
      if (frame) globalThis.cancelAnimationFrame?.(frame);
      frame = globalThis.requestAnimationFrame?.(measure) || 0;
      if (!frame) measure();
    };

    measure();
    viewport?.addEventListener("resize", schedule);
    viewport?.addEventListener("scroll", schedule);
    globalThis.addEventListener("resize", schedule);
    return () => {
      if (frame) globalThis.cancelAnimationFrame?.(frame);
      viewport?.removeEventListener("resize", schedule);
      viewport?.removeEventListener("scroll", schedule);
      globalThis.removeEventListener("resize", schedule);
    };
  }, [rootRef]);
}
