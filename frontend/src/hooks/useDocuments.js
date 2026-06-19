import { useState, useEffect } from "react"

export function useDocuments({ API_BASE, activeTab }) {
  const [documents, setDocuments] = useState([])
  const [docLoading, setDocLoading] = useState(false)
  const [docError, setDocError] = useState("")
  const [uploading, setUploading] = useState(false)

  const fetchDocuments = async () => {
    setDocLoading(true); setDocError("")
    try {
      const r = await fetch(`${API_BASE}/api/knowledge`)
      if (!r.ok) { setDocError(`Ошибка ${r.status}`); setDocLoading(false); return }
      const d = await r.json()
      setDocuments(d.documents || d.items || [])
    } catch { setDocError("Не удалось загрузить документы") }
    setDocLoading(false)
  }

  useEffect(() => { if (activeTab === "documents") fetchDocuments() }, [activeTab])

  const handleFileUpload = async (file) => {
    setUploading(true)
    try {
      const fd = new FormData(); fd.append("file", file)
      await fetch(`${API_BASE}/api/knowledge/upload`, { method: "POST", body: fd })
      await fetchDocuments()
    } catch { setDocError("Ошибка загрузки") }
    setUploading(false)
  }

  return { documents, docLoading, docError, uploading, fetchDocuments, handleFileUpload }
}
