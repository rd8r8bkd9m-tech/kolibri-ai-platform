import { Skeleton } from "../ui/Skeleton"

export function DocumentsPanel({ documents, docLoading, docError, uploading, fileInputRef, onUpload }) {
  return (
    <div className="control-section">
      <div className="control-section-head">
        <h3>Документы</h3>
        <input ref={fileInputRef} type="file" onChange={onUpload} style={{display:"none"}} accept=".pdf,.txt,.md,.doc,.docx,.csv,.json" />
        <button className="upload-btn" onClick={() => fileInputRef.current?.click()} disabled={uploading}>
          {uploading ? "Загрузка..." : "+ Загрузить"}
        </button>
      </div>
      {docError && <div className="doc-error">{docError}</div>}
      {docLoading ? (
        <div className="skeleton-list">{[1,2,3].map(i => <Skeleton key={i} className="skeleton-item" />)}</div>
      ) : documents.length === 0 ? (
        <div className="doc-empty compact">
          <p>Нет документов</p>
          <p className="doc-empty-hint">Загрузите файлы для анализа</p>
        </div>
      ) : (
        <div className="doc-list">
          {documents.map((doc, i) => (
            <div key={i} className="doc-item">
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
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
