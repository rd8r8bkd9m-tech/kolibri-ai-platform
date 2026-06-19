import { motion } from "framer-motion"
import { Skeleton } from "./Skeleton"

export function SearchView({ searchQuery, setSearchQuery, searchResults, searchLoading, onSearch }) {
  const handleKeyDown = (e) => { if (e.key === "Enter") onSearch() }

  return (
    <motion.div key="search" className="documents-panel" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
      <div className="documents-header"><h2>Поиск</h2></div>
      <div style={{ marginBottom: "20px" }}>
        <div className="input-wrapper" style={{ maxWidth: "600px" }}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted)" strokeWidth="2" style={{ flexShrink: 0 }}>
            <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
          </svg>
          <input type="text" value={searchQuery} onChange={e => setSearchQuery(e.target.value)}
            onKeyDown={handleKeyDown} aria-label="Поиск по базе знаний"
            placeholder="Поиск по базе знаний..."
            style={{ flex:1, border:"none", background:"transparent", color:"var(--text-primary)", fontSize:"14px", fontFamily:"var(--font-ui)", outline:"none", padding:"8px 0" }} />
          <motion.button className="send-btn" style={{ width:"36px", height:"36px" }} onClick={onSearch} aria-label="Найти"
            whileHover={{ scale: 1.08 }} whileTap={{ scale: 0.92 }}>
            {searchLoading ? (
              <motion.svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
                animate={{ rotate: 360 }} transition={{ duration: 1, repeat: Infinity, ease: "linear" }}>
                <path d="M21 12a9 9 0 11-6.219-8.56"/>
              </motion.svg>
            ) : (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>
            )}
          </motion.button>
        </div>
      </div>
      {searchLoading ? (
        <div className="skeleton-list">{[1,2,3].map(i => <Skeleton key={i} className="skeleton-item" />)}</div>
      ) : searchResults.length > 0 ? (
        <div className="doc-list">
          {searchResults.map((r, i) => (
            <motion.div key={i} className="doc-item" initial={{ opacity: 0 }} animate={{ opacity: 1 }}
              transition={{ delay: i * 0.05 }} whileHover={{ x: 4 }}>
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
            </motion.div>
          ))}
        </div>
      ) : (
        <div className="doc-empty">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" style={{opacity:0.3,marginBottom:16}}>
            <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
          </svg>
          <p>Семантический поиск</p>
          <p className="doc-empty-hint">Введите запрос для поиска по базе знаний</p>
        </div>
      )}
    </motion.div>
  )
}
