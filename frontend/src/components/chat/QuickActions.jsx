import { motion } from "framer-motion"

export const DEFAULT_QUICK_ACTIONS = [
  { title: "Смета", desc: "Расчёт работ и материалов", color: "purple", prompt: "Создай строительную смету для " },
  { title: "КП", desc: "Коммерческое предложение", color: "green", prompt: "Подготовь коммерческое предложение по смете: " },
  { title: "Документы", desc: "Договор, акт, счёт", color: "blue", prompt: "Создай полный пакет документов для " },
  { title: "Подписка", desc: "Тарифы и оплата", color: "orange", control: "billing" },
]

export function QuickActions({ actions = DEFAULT_QUICK_ACTIONS, onPrompt, onControl }) {
  return (
    <div className="quick-actions">
      {actions.map((action, i) => (
        <motion.button key={action.title} className="quick-action"
          initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.5 + i * 0.08, type: "spring", stiffness: 200 }}
          whileHover={{ scale: 1.03, y: -3 }} whileTap={{ scale: 0.97 }}
          onClick={() => action.control ? onControl(action.control) : onPrompt(action.prompt)}>
          <div className={`quick-action-icon ${action.color}`}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14,2 14,8 20,8"/><line x1="16" y1="13" x2="8" y2="13"/>
            </svg>
          </div>
          <div className="quick-action-text">
            <div className="quick-action-title">{action.title}</div>
            <div className="quick-action-desc">{action.desc}</div>
          </div>
        </motion.button>
      ))}
    </div>
  )
}
