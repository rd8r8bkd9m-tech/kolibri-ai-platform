import { motion } from "framer-motion"
import { KolibriBird } from "./KolibriBird"

export function WelcomeScreen({ quickActions, onAction }) {
  return (
    <motion.div className="welcome" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.6 }}>
      <motion.div initial={{ scale: 0.8, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
        transition={{ type: "spring", stiffness: 200, delay: 0.1 }}>
        <KolibriBird size={180} state="idle" />
      </motion.div>
      <motion.h1 className="welcome-title" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.3 }}>Kolibri AI</motion.h1>
      <motion.p className="welcome-subtitle" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.4 }}>Чем могу помочь?</motion.p>
      <div className="quick-actions">
        {quickActions.map((a, i) => (
          <motion.button key={a.title} className="quick-action"
            initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.5 + i * 0.08, type: "spring", stiffness: 200 }}
            whileHover={{ scale: 1.03, y: -3 }} whileTap={{ scale: 0.97 }}
            onClick={() => onAction(a)}>
            <div className={`quick-action-icon ${a.color}`}>{a.icon}</div>
            <div className="quick-action-text">
              <div className="quick-action-title">{a.title}</div>
              <div className="quick-action-desc">{a.desc}</div>
            </div>
          </motion.button>
        ))}
      </div>
    </motion.div>
  )
}
