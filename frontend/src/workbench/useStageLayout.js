import { useEffect, useLayoutEffect, useState } from "react";

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
  const [mobile, setMobile] = useState(() => globalThis.innerWidth < 760);
  useEffect(() => {
    const update = () => setMobile(globalThis.innerWidth < 760);
    globalThis.addEventListener("resize", update);
    return () => globalThis.removeEventListener("resize", update);
  }, []);
  return mobile;
}
