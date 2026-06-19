import { useState } from "react"

export function useConversations({ API_BASE, setMessages, setActiveTab, setSidebar, setGlobalError }) {
  const [conversations, setConversations] = useState([])
  const [conversationId, setConversationId] = useState(null)
  const [convLoading, setConvLoading] = useState(false)

  const fetchConversations = async () => {
    try {
      const r = await fetch(`${API_BASE}/api/conversations`)
      if (r.ok) setConversations(await r.json())
    } catch (e) { console.error("Failed to fetch conversations", e) }
  }

  const loadLastConversation = async () => {
    setConvLoading(true)
    try {
      const r = await fetch(`${API_BASE}/api/conversations`)
      if (r.ok) {
        const convs = await r.json()
        if (convs.length > 0) {
          const last = convs[0]
          setConversationId(last.id)
          const mr = await fetch(`${API_BASE}/api/conversations/${last.id}/messages`)
          if (mr.ok) {
            const msgs = await mr.json()
            if (msgs.length > 0) {
              setMessages(msgs.map(m => ({ role: m.role, content: m.content, provider: m.provider, timestamp: m.created_at ? new Date(m.created_at).getTime() : Date.now() })))
            }
          }
        }
      }
    } catch (e) { console.error("Failed to load last conversation", e) }
    setConvLoading(false)
  }

  const loadConversation = async (id) => {
    setConvLoading(true)
    try {
      const r = await fetch(`${API_BASE}/api/conversations/${id}/messages`)
      if (r.ok) {
        const msgs = await r.json()
        setMessages(msgs.map(m => ({ role: m.role, content: m.content, provider: m.provider, timestamp: m.created_at ? new Date(m.created_at).getTime() : Date.now() })))
        setConversationId(id)
        setActiveTab("chat")
        setSidebar(false)
      }
    } catch { setGlobalError("Не удалось загрузить диалог") }
    setConvLoading(false)
  }

  const deleteConversation = async (id) => {
    try {
      const r = await fetch(`${API_BASE}/api/conversations/${id}`, { method: "DELETE" })
      if (!r.ok) { setGlobalError("Не удалось удалить диалог"); return }
      if (id === conversationId) { setConversationId(null); setMessages([]) }
      fetchConversations()
    } catch { setGlobalError("Ошибка удаления") }
  }

  return {
    conversations, conversationId, setConversationId, convLoading,
    fetchConversations, loadLastConversation, loadConversation, deleteConversation,
  }
}
