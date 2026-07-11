import { motion } from "framer-motion";
import { X } from "lucide-react";

export function MobileWindow({ windowState, dispatch, onFocus, renderContent }) {
  const isProjectSurface = windowState.kind === "workspace";
  const deactivate = () => dispatch({ type: "DEACTIVATE", id: windowState.id });
  return (
    <motion.div
      animate={{ opacity: 1, y: 0 }}
      className={`mobile-window-layer ${isProjectSurface ? "is-surface" : "is-sheet"}`}
      exit={{ opacity: 0, y: isProjectSurface ? 12 : 36 }}
      initial={{ opacity: 0, y: isProjectSurface ? 12 : 36 }}
      onPointerDown={() => onFocus?.(windowState)}
      transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
    >
      {!isProjectSurface && <button aria-label="Закрыть панель" className="mobile-sheet-scrim" onClick={deactivate} type="button" />}
      <article className="mobile-window" data-testid={`window-${windowState.kind}`}>
        <header>
          <div><strong>{windowState.title}</strong><span>{windowState.payload?.statusLabel || "Kolibri workspace"}</span></div>
          <button aria-label="Закрыть окно" onClick={deactivate} type="button"><X size={19} /></button>
        </header>
        <div className="window-content">{renderContent(windowState)}</div>
      </article>
    </motion.div>
  );
}
