import { motion } from "framer-motion"

export function EstimateFolderCard({ data, onClick }) {
  const title = data?.title || "Смета"
  const items = data?.items || []
  const total = data?.totals?.grand_total || 0
  const sections = [...new Set(items.map(i => i.section).filter(Boolean))]

  const formatNum = (n) => {
    if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`
    if (n >= 1000) return `${(n / 1000).toFixed(0)}K`
    return n.toLocaleString("ru-RU")
  }

  return (
    <motion.div
      className="estimate-folder"
      onClick={onClick}
      initial={{ opacity: 0, y: 20, scale: 0.95 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.4, type: "spring", stiffness: 200 }}
      whileHover={{ scale: 1.02, y: -4 }}
      whileTap={{ scale: 0.98 }}
    >
      <div className="estimate-folder__tabs">
        <div className="estimate-folder__tab estimate-folder__tab--active" />
        <div className="estimate-folder__tab" />
        <div className="estimate-folder__tab" />
      </div>

      <div className="estimate-folder__body">
        <div className="estimate-folder__icon">
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
            <polyline points="14,2 14,8 20,8" />
            <line x1="16" y1="13" x2="8" y2="13" />
            <line x1="16" y1="17" x2="8" y2="17" />
            <polyline points="10,9 9,9 8,9" />
          </svg>
        </div>

        <div className="estimate-folder__info">
          <div className="estimate-folder__label">СМЕТА</div>
          <div className="estimate-folder__title">{title}</div>
          <div className="estimate-folder__meta">
            <span>{items.length} поз.</span>
            {sections.length > 0 && <span> · {sections.length} раздел.</span>}
          </div>
        </div>

        <div className="estimate-folder__total">
          <div className="estimate-folder__amount">{formatNum(total)}</div>
          <div className="estimate-folder__currency">руб.</div>
        </div>
      </div>

      <div className="estimate-folder__footer">
        <div className="estimate-folder__sections">
          {sections.slice(0, 3).map((s, i) => (
            <span key={i} className="estimate-folder__section-tag">{s}</span>
          ))}
          {sections.length > 3 && <span className="estimate-folder__section-more">+{sections.length - 3}</span>}
        </div>
        <div className="estimate-folder__action">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <polyline points="9 18 15 12 9 6" />
          </svg>
        </div>
      </div>
    </motion.div>
  )
}
