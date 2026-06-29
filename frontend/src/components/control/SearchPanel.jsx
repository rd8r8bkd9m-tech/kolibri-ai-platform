import { motion } from "framer-motion"
import { Skeleton } from "../ui/Skeleton"

export function SearchPanel({ query, setQuery, results, loading, onSearch }) {
  return (
    <div className="control-section">
      <div className="control-section-head"><h3>Поиск</h3></div>
      <div className="input-wrapper control-search">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted)" strokeWidth="2" style={{ flexShrink: 0 }}>
          <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
        </svg>
        <input type="text" value={query} onChange={e => setQuery(e.target.value)}
          onKeyDown={e => e.key === "Enter" && onSearch()}
          placeholder="Поиск по базе знаний..." />
        <button className="send-btn" style={{ width:"36px", height:"36px" }} onClick={onSearch}>
          {loading ? (
            <motion.svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
              animate={{ rotate: 360 }} transition={{ duration: 1, repeat: Infinity, ease: "linear" }}>
              <path d="M21 12a9 9 0 11-6.219-8.56"/>
            </motion.svg>
          ) : (
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>
          )}
        </button>
      </div>
      {loading ? (
        <div className="skeleton-list">{[1,2,3].map(i => <Skeleton key={i} className="skeleton-item" />)}</div>
      ) : results.length > 0 ? (
        <div className="doc-list">
          {results.map((r, i) => (
            <div key={i} className="doc-item">
              <div className="doc-icon" style={{ background:"var(--accent-soft)", color:"var(--accent)" }}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
                </svg>
              </div>
              <div className="doc-info">
                <div className="doc-name">{r.title || r.filename || `Результат ${i+1}`}</div>
                <div className="doc-meta">{r.content?.substring(0, 120)}...</div>
              </div>
              {r.score && <span className="doc-badge ready">{Math.round(r.score * 100)}%</span>}
            </div>
          ))}
        </div>
      ) : (
        <div className="doc-empty compact">
          <p>Семантический поиск</p>
          <p className="doc-empty-hint">Введите запрос</p>
        </div>
      )}
    </div>
  )
}
