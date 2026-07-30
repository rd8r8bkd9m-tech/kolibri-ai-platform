import { useEffect, useLayoutEffect, useState } from "react";

const MOBILE_SURFACE_QUERY = "(max-width: 760px)";

export function useStageBounds(ref) {
  const [bounds, setBounds] = useState({ width: 1280, height: 720 });
  useLayoutEffect(() => {
    const stage = ref.current;
    if (!stage) return undefined;
    const measure = () => {
      // ResizeObserver may deliver one last queued callback after React has
      // detached the ref. Measure the element captured by this effect rather
      // than dereferencing a ref that can legitimately become null.
      if (!stage.isConnected) return;
      const rect = stage.getBoundingClientRect();
      setBounds({
        width: Math.max(560, Math.floor(rect.width)),
        height: Math.max(420, Math.floor(rect.height)),
      });
    };
    measure();
    const observer = globalThis.ResizeObserver ? new ResizeObserver(measure) : null;
    observer?.observe(stage);
    window.addEventListener("resize", measure);
    return () => {
      observer?.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, [ref]);
  return bounds;
}

export function useMobileSurface() {
  const [mobile, setMobile] = useState(() => globalThis.matchMedia?.(MOBILE_SURFACE_QUERY).matches ?? globalThis.innerWidth <= 760);
  useEffect(() => {
    const media = globalThis.matchMedia?.(MOBILE_SURFACE_QUERY);
    if (!media) return undefined;
    const update = () => setMobile(media.matches);
    update();
    media.addEventListener?.("change", update);
    return () => media.removeEventListener?.("change", update);
  }, []);
  return mobile;
}
