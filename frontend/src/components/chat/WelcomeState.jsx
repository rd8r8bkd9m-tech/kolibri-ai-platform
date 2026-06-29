import { motion } from "framer-motion"
import { KolibriBird } from "../KolibriBird"
import { QuickActions } from "./QuickActions"

export function WelcomeState({ onPrompt, onControl }) {
  return (
    <motion.div className="welcome" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.6 }}>
      <motion.div initial={{ scale: 0.8, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
        transition={{ type: "spring", stiffness: 200, delay: 0.1 }}>
        <KolibriBird size={90} state="idle" />
      </motion.div>
      <motion.h1 className="welcome-title" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.3 }}>Kolibri AI</motion.h1>
      <motion.p className="welcome-subtitle" initial={{ opacity: 0 }} animate={{ opacity: 1 }}
        transition={{ delay: 0.4 }}>
        Строительные сметы, КП и документы через чат
      </motion.p>
      <QuickActions onPrompt={onPrompt} onControl={onControl} />
    </motion.div>
  )
}
