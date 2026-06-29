import { AnimatePresence, motion } from "framer-motion"

export function ControlPanel({ open, active, setActive, onClose, plugins, children }) {
  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div className="control-scrim" onClick={onClose} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} />
          <motion.aside
            className="control-panel"
            initial={{ opacity: 0, y: 16, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 16, scale: 0.98 }}
            transition={{ duration: 0.18 }}
          >
            <div className="control-header">
              <div>
                <div className="control-title">Контрол</div>
                <div className="control-subtitle">Kolibri AI</div>
              </div>
              <button className="header-btn" onClick={onClose} title="Закрыть">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                </svg>
              </button>
            </div>
            <div className="control-tabs">
              {plugins.map(plugin => (
                <button key={plugin.id} className={`control-tab ${active === plugin.tab ? "active" : ""}`} onClick={() => setActive(plugin.tab)}>
                  {plugin.title}
                </button>
              ))}
            </div>
            <div className="control-body">{children}</div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  )
}
