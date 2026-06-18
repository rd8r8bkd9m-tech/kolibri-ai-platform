import { useRef } from "react"
import { motion } from "framer-motion"
import { Skeleton } from "./Skeleton"

export function DocumentsView({ documents, docLoading, docError, uploading, onUpload }) {
  const fileInputRef = useRef(null)

  const handleFileUpload = async (e) => {
    const file = e.target.files?.[0]; if (!file) return
    onUpload(file)
  }

  return (
    <motion.div key="docs" className="documents-panel" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
      <div className="documents-header">
        <h2>Документы</h2>
        <input ref={fileInputRef} type="file" onChange={handleFileUpload} style={{display:"none"}} accept=".pdf,.txt,.md,.doc,.docx,.csv,.json" />
        <motion.button className="upload-btn" onClick={() => fileInputRef.current?.click()} disabled={uploading}
          whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }}>
          {uploading ? "Загрузка..." : "+ Загрузить"}
        </motion.button>
      </div>
      {docError && <div className="doc-error">{docError}</div>}
      {docLoading ? (
        <div className="skeleton-list">{[1,2,3].map(i => <Skeleton key={i} className="skeleton-item" />)}</div>
      ) : documents.length === 0 ? (
        <div className="doc-empty">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" style={{opacity:0.3,marginBottom:16}}>
            <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14,2 14,8 20,8"/>
          </svg>
          <p>Нет документов</p>
          <p className="doc-empty-hint">Загрузите файлы для анализа</p>
        </div>
      ) : (
        <div className="doc-list">
          {documents.map((doc, i) => (
            <motion.div key={i} className="doc-item" initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.05 }} whileHover={{ x: 4 }}>
              <div className="doc-icon">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14,2 14,8 20,8"/>
                </svg>
              </div>
              <div className="doc-info">
                <div className="doc-name">{doc.filename || doc.name || `Документ ${i+1}`}</div>
                <div className="doc-meta">{doc.size || ""}</div>
              </div>
              {doc.status === "processed" && <span className="doc-badge ready">Готов</span>}
            </motion.div>
          ))}
        </div>
      )}
    </motion.div>
  )
}
