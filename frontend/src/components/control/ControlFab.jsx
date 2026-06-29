import { motion } from "framer-motion"

export function ControlFab({ open, onClick }) {
  return (
    <motion.button
      className={`control-fab ${open ? "open" : ""}`}
      onClick={onClick}
      type="button"
      aria-label={open ? "Закрыть Контрол" : "Открыть Контрол"}
      aria-pressed={open}
      whileHover={{ scale: 1.04 }}
      whileTap={{ scale: 0.96 }}
    >
      <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M4 21v-7"/><path d="M4 10V3"/><path d="M12 21v-9"/><path d="M12 8V3"/><path d="M20 21v-5"/><path d="M20 12V3"/><path d="M2 14h4"/><path d="M10 8h4"/><path d="M18 16h4"/>
      </svg>
      <span>Контрол</span>
    </motion.button>
  )
}
