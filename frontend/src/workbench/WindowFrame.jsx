import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { ChevronsRight, Maximize2, Minimize2, Minus, X } from "lucide-react";

export function WindowFrame({ windowState, bounds, focused, dispatch, onFocus, renderContent }) {
  const [gesture, setGesture] = useState(null);

  useEffect(() => {
    if (!gesture) return undefined;
    const move = (event) => {
      event.preventDefault();
      if (gesture.kind === "drag") {
        dispatch({ type: "MOVE", id: windowState.id, x: event.clientX - gesture.dx, y: event.clientY - gesture.dy, bounds });
      } else {
        dispatch({
          type: "RESIZE",
          id: windowState.id,
          width: event.clientX - gesture.left,
          height: event.clientY - gesture.top,
          bounds,
        });
      }
    };
    const finish = () => setGesture(null);
    globalThis.addEventListener("pointermove", move, { passive: false });
    globalThis.addEventListener("pointerup", finish);
    globalThis.addEventListener("pointercancel", finish);
    return () => {
      globalThis.removeEventListener("pointermove", move);
      globalThis.removeEventListener("pointerup", finish);
      globalThis.removeEventListener("pointercancel", finish);
    };
  }, [bounds, dispatch, gesture, windowState.id]);

  const style = windowState.maximized
    ? { inset: 0, zIndex: windowState.z }
    : {
        left: windowState.x,
        top: windowState.y,
        width: windowState.width,
        height: windowState.height,
        zIndex: windowState.z,
      };

  const focus = () => {
    dispatch({ type: "FOCUS", id: windowState.id });
    onFocus?.(windowState);
  };

  const startDrag = (event) => {
    if (event.button !== 0 || windowState.maximized || event.target.closest?.("button")) return;
    const frame = event.currentTarget?.closest?.(".stage-window");
    if (!frame) return;
    const rect = frame.getBoundingClientRect();
    setGesture({ kind: "drag", dx: event.clientX - rect.left, dy: event.clientY - rect.top });
    focus();
  };

  const startResize = (event) => {
    if (event.button !== 0 || windowState.maximized) return;
    event.stopPropagation();
    const frame = event.currentTarget?.closest?.(".stage-window");
    if (!frame) return;
    const rect = frame.getBoundingClientRect();
    setGesture({ kind: "resize", left: rect.left, top: rect.top });
    focus();
  };

  return (
    <motion.article
      animate={{ opacity: 1, scale: 1, y: 0 }}
      className={`stage-window ${focused ? "is-focused" : ""} ${windowState.maximized ? "is-maximized" : ""}`}
      data-testid={`window-${windowState.kind}`}
      exit={{ opacity: 0, scale: 0.94, y: 18 }}
      initial={{ opacity: 0, scale: 0.985, y: 8 }}
      onPointerDown={focus}
      style={style}
      transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
    >
      <header className="window-bar" onDoubleClick={() => dispatch({ type: "MAXIMIZE", id: windowState.id })} onPointerDown={startDrag}>
        <div className="window-title">
          <strong>{windowState.title}</strong>
          <span>{windowState.payload?.statusLabel || "Kolibri workspace"}</span>
        </div>
        <nav aria-label="Управление окном" className="window-actions">
          <button aria-label="Свернуть" onClick={(event) => { event.stopPropagation(); dispatch({ type: "MINIMIZE", id: windowState.id }); }} type="button"><Minus size={16} /></button>
          <button aria-label={windowState.maximized ? "Восстановить размер" : "Развернуть"} onClick={(event) => { event.stopPropagation(); dispatch({ type: "MAXIMIZE", id: windowState.id }); }} type="button">
            {windowState.maximized ? <Minimize2 size={15} /> : <Maximize2 size={15} />}
          </button>
          <button aria-label="Закрыть окно" onClick={(event) => { event.stopPropagation(); dispatch({ type: "DEACTIVATE", id: windowState.id }); }} type="button"><X size={17} /></button>
        </nav>
      </header>
      <div className="window-content">{renderContent(windowState)}</div>
      {!windowState.maximized && <button aria-label="Изменить размер окна" className="window-resize" onPointerDown={startResize} type="button"><ChevronsRight size={15} /></button>}
    </motion.article>
  );
}
