import { motion } from "framer-motion";
import { useCallback, useRef } from "react";
import { useDialogFocus } from "../app/useDialogFocus";
import { MobileWindowHeader } from "./MobileWindowHeader";
import { isMobileFullSurface } from "./mobileWindowModel";

export function MobileWindow({ windowState, dispatch, onFocus, renderContent }) {
  const dialog = useRef(null);
  const isFullSurface = isMobileFullSurface(windowState.kind);
  const labelId = `mobile-window-${String(windowState.id).replace(/[^a-z0-9_-]/gi, "-")}-title`;
  const deactivate = useCallback(() => dispatch({ type: "DEACTIVATE", id: windowState.id }), [dispatch, windowState.id]);
  useDialogFocus(dialog, { onEscape: deactivate, fallbackFocus: "#kolibri-navigation-trigger" });
  return (
    <motion.div
      animate={{ opacity: 1, y: 0 }}
      className={`mobile-window-layer ${isFullSurface ? "is-surface" : "is-sheet"}`}
      exit={{ opacity: 0, y: isFullSurface ? 12 : 36 }}
      initial={{ opacity: 0, y: isFullSurface ? 12 : 36 }}
      onPointerDown={() => onFocus?.(windowState)}
      transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
    >
      {!isFullSurface && <button aria-label="Закрыть панель" className="mobile-sheet-scrim" onClick={deactivate} type="button" />}
      <article aria-labelledby={labelId} aria-modal="true" className="mobile-window" data-testid={`window-${windowState.kind}`} ref={dialog} role="dialog" tabIndex={-1}>
        <MobileWindowHeader labelId={labelId} onClose={deactivate} status={windowState.payload?.statusLabel || "Kolibri workspace"} title={windowState.title} />
        <div className="window-content">{renderContent(windowState)}</div>
      </article>
    </motion.div>
  );
}
