import { AnimatePresence } from "framer-motion";
import { useMemo, useRef } from "react";
import { ChevronsLeft } from "lucide-react";
import { MobileWindow } from "./MobileWindow";
import { WindowFrame } from "./WindowFrame";
import { useMobileSurface, useStageBounds } from "./useStageLayout";

function PrimarySurface({ children, inert = false }) {
  return <div className="primary-surface" data-testid="primary-surface" inert={inert}>{children}</div>;
}

export function Workbench({ windows, focusedId, dispatch, onFocus, renderContent, renderPrimary }) {
  const stageRef = useRef(null);
  const bounds = useStageBounds(stageRef);
  const mobile = useMobileSurface();
  const visible = useMemo(() => windows.filter((item) => !item.minimized), [windows]);
  const top = visible.length ? visible.reduce((left, right) => left.z > right.z ? left : right) : null;

  if (mobile) {
    return (
      <section className="mobile-stage" data-testid="mobile-stage">
        <PrimarySurface inert={Boolean(top)}>{renderPrimary()}</PrimarySurface>
        <AnimatePresence>{top && <MobileWindow dispatch={dispatch} key={top.id} onFocus={onFocus} renderContent={renderContent} windowState={top} />}</AnimatePresence>
      </section>
    );
  }

  return (
    <section className="stage-canvas" data-testid="stage-canvas" ref={stageRef}>
      <PrimarySurface>{renderPrimary()}</PrimarySurface>
      <AnimatePresence>
        {visible.map((item) => (
          <WindowFrame
            bounds={bounds}
            dispatch={dispatch}
            focused={focusedId === item.id || (!focusedId && top?.id === item.id)}
            key={item.id}
            onFocus={onFocus}
            renderContent={renderContent}
            windowState={item}
          />
        ))}
      </AnimatePresence>
      <span className="stage-edge-hint" aria-hidden="true"><ChevronsLeft size={15} /></span>
    </section>
  );
}
