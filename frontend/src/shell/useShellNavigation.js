import { useEffect, useReducer, useRef } from "react";
import { useMobileSurface } from "../workbench/useStageLayout";
import { initialShellNavigation, shellNavigationReducer } from "./shellNavigationModel";
const PINNED_KEY = "kolibri.shell.navigation-pinned.v1";

function readPinned() {
  try {
    return globalThis.localStorage?.getItem(PINNED_KEY) === "true";
  } catch {
    return false;
  }
}

function focusNavigationTrigger() {
  globalThis.requestAnimationFrame?.(() => globalThis.document?.getElementById("kolibri-navigation-trigger")?.focus());
}
export function useShellNavigation() {
  const mobile = useMobileSurface();
  const [state, dispatch] = useReducer(shellNavigationReducer, { ...initialShellNavigation, pinned: readPinned() });
  const previewTimer = useRef(null);

  useEffect(() => {
    try { globalThis.localStorage?.setItem(PINNED_KEY, String(state.pinned)); } catch { /* private mode */ }
  }, [state.pinned]);

  useEffect(() => {
    if (!state.mobileOpen) return undefined;
    const close = (event) => {
      if (event.key !== "Escape") return;
      dispatch({ type: "DISMISS" });
      focusNavigationTrigger();
    };
    globalThis.addEventListener("keydown", close);
    return () => globalThis.removeEventListener("keydown", close);
  }, [state.mobileOpen]);
  useEffect(() => () => globalThis.clearTimeout(previewTimer.current), []);

  const clearPreviewTimer = () => globalThis.clearTimeout(previewTimer.current);
  const openPreview = () => {
    if (mobile || state.pinned) return;
    clearPreviewTimer();
    dispatch({ type: "PREVIEW_OPEN" });
  };
  const closePreview = () => {
    if (mobile || state.pinned) return;
    clearPreviewTimer();
    previewTimer.current = globalThis.setTimeout(() => dispatch({ type: "PREVIEW_CLOSE" }), 180);
  };

  const dismiss = () => {
    clearPreviewTimer();
    dispatch({ type: "DISMISS" });
    if (mobile) focusNavigationTrigger();
  };
  const toggle = () => {
    if (mobile) {
      dispatch({ type: "MOBILE_TOGGLE" });
      return;
    }
    clearPreviewTimer();
    dispatch({ type: "PIN_TOGGLE" });
  };

  return {
    dismiss,
    expanded: mobile ? state.mobileOpen : state.pinned || state.preview,
    layoutPinned: !mobile && state.pinned,
    mobile,
    mobileOpen: state.mobileOpen,
    onPointerEnter: openPreview,
    onPointerLeave: closePreview,
    pinned: state.pinned,
    preview: !mobile && state.preview && !state.pinned,
    toggle,
  };
}
