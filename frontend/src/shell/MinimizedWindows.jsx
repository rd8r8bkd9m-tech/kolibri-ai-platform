import { AnimatePresence, motion } from "framer-motion";
import { AppWindow } from "lucide-react";

export function MinimizedWindows({ expanded, windows, onRestore }) {
  if (!windows.length) return null;
  return (
    <div aria-label="Свёрнутые окна" className="minimized-dock">
      {expanded && <small className="dock-section-label">Свёрнуто</small>}
      <AnimatePresence initial={false}>
        {windows.map((windowState) => (
          <motion.button
            animate={{ opacity: 1, scale: 1 }}
            aria-label={`Открыть ${windowState.title}`}
            exit={{ opacity: 0, scale: 0.72 }}
            initial={{ opacity: 0, scale: 0.72 }}
            key={windowState.id}
            layout
            onClick={() => onRestore(windowState.id)}
            title={windowState.title}
            transition={{ duration: 0.16 }}
            type="button"
          >
            <AppWindow size={18} />
            <span>{windowState.title}</span>
          </motion.button>
        ))}
      </AnimatePresence>
    </div>
  );
}
