import { useState, useEffect, useRef } from "react"
import { motion, AnimatePresence } from "framer-motion"
import "./App.css"
import { KolibriCompanion } from "./components/KolibriCompanion"
import { Sidebar } from "./components/Sidebar"
import { ErrorBoundary } from "./components/ErrorBoundary"
import { ChatView } from "./components/ChatView"
import { DocumentsView } from "./components/DocumentsView"
import { SearchView } from "./components/SearchView"
import { ClusterView } from "./components/ClusterView"
import { BottomSheet } from "./components/BottomSheet"
import { EstimateEditor } from "./features/estimates/EstimateEditor"
import { useWebSocket } from "./hooks/useWebSocket"
import { useConversations } from "./hooks/useConversations"
import { useDocuments } from "./hooks/useDocuments"
import { useCluster } from "./hooks/useCluster"
import { useSearch } from "./hooks/useSearch"

const API_BASE = ""

export default function App() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState("")
  const [loading, setLoading] = useState(false)
  const [providers, setProviders] = useState([])
  const [selectedProvider, setSelectedProvider] = useState("mimo")
  const [sidebar, setSidebar] = useState(false)
  const [theme, setTheme] = useState(() => localStorage.getItem("kolibri-theme") || "dark")
  const [activeTab, setActiveTab] = useState("chat")
  const [estimateEditor, setEstimateEditor] = useState(null)
  const [globalError, setGlobalError] = useState("")
  const messagesRef = useRef(null)
  const inputRef = useRef(null)

  const { ws, connected, connectWS } = useWebSocket({ setMessages, setLoading })
  const {
    conversations, conversationId, setConversationId, convLoading,
    fetchConversations, loadLastConversation, loadConversation, deleteConversation,
  } = useConversations({ API_BASE, setMessages, setActiveTab, setSidebar, setGlobalError })
  const { documents, docLoading, docError, uploading, handleFileUpload } = useDocuments({ API_BASE, activeTab })
  const { clusterStatus, fetchCluster } = useCluster({ API_BASE })
  const { searchQuery, setSearchQuery, searchResults, searchLoading, handleSearch } = useSearch({ API_BASE })

  useEffect(() => {
    const root = document.documentElement
    root.classList.remove("theme-dark", "theme-light")
    root.classList.add(theme === "dark" ? "theme-dark" : "theme-light")
    localStorage.setItem("kolibri-theme", theme)
    document.querySelector('meta[name="theme-color"]')?.setAttribute("content", theme === "dark" ? "#0a0a0f" : "#f0f4f8")
  }, [theme])

  useEffect(() => {
    fetch(`${API_BASE}/api/providers`).then(r => r.json()).then(setProviders).catch((e) => console.error("Failed to fetch providers", e))
    connectWS()
    fetchCluster()
    loadLastConversation()
    const ci = setInterval(fetchCluster, 15000)

    let touchStartX = 0
    let touchStartY = 0
    const onTouchStart = (e) => {
      touchStartX = e.touches[0].clientX
      touchStartY = e.touches[0].clientY
    }
    const onTouchMove = (e) => {
      if (!touchStartX) return
      const dx = e.touches[0].clientX - touchStartX
      const dy = Math.abs(e.touches[0].clientY - touchStartY)
      if (touchStartX < 50 && dx > 30 && dy < 80) {
        setSidebar(true)
        touchStartX = 0
      }
    }
    const onTouchEnd = () => { touchStartX = 0 }
    document.addEventListener("touchstart", onTouchStart, { passive: true })
    document.addEventListener("touchmove", onTouchMove, { passive: true })
    document.addEventListener("touchend", onTouchEnd, { passive: true })
    return () => {
      if (ws) ws.close()
      clearInterval(ci)
      document.removeEventListener("touchstart", onTouchStart)
      document.removeEventListener("touchmove", onTouchMove)
      document.removeEventListener("touchend", onTouchEnd)
    }
  }, [])

  useEffect(() => {
    if (messagesRef.current) messagesRef.current.scrollTo({ top: messagesRef.current.scrollHeight, behavior: "smooth" })
  }, [messages])

  useEffect(() => { fetchConversations() }, [])

  const sendMessage = async () => {
    if (!input.trim() || loading) return
    const userMsg = { role: "user", content: input, timestamp: Date.now() }
    const newMsgs = [...messages, userMsg]
    setMessages(newMsgs); setInput(""); setLoading(true)
    setMessages([...newMsgs, { role: "assistant", content: "", streaming: true, provider: "", timestamp: Date.now() }])

    let convId = conversationId
    if (!convId) {
      try {
        const r = await fetch(`${API_BASE}/api/conversations`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ title: input.slice(0, 80) })
        })
        if (r.ok) { const c = await r.json(); convId = c.id; setConversationId(convId) }
      } catch (e) { console.error("Failed to create conversation", e) }
    }

    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ messages: newMsgs.map(m => ({ role: m.role, content: m.content })), provider: selectedProvider, conversation_id: convId }))
    } else {
      try {
        const r = await fetch(`${API_BASE}/api/chat`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ messages: newMsgs, provider: selectedProvider, conversation_id: convId }) })
        const d = await r.json()
        const assistantMsg = { role: "assistant", content: d.response, provider: d.provider, timestamp: Date.now() }
        if (d.canvas) assistantMsg.canvas = d.canvas
        setMessages([...newMsgs, assistantMsg])
      } catch { setMessages([...newMsgs, { role: "assistant", content: "Ошибка подключения к серверу.", timestamp: Date.now() }]) }
      setLoading(false)
    }
    fetchConversations()
  }

  const quickActions = [
    { icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>, title: "Чат с AI", desc: "Задайте вопрос", color: "blue", prompt: "" },
    { icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14,2 14,8 20,8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>, title: "Смета", desc: "AI-генерация сметы", color: "purple", prompt: "Создай строительную смету для " },
    { icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 002 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0022 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg>, title: "Документы", desc: "Пакет документов", color: "green", prompt: "Создай полный пакет документов для " },
    { icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>, title: "Поиск", desc: "База знаний", color: "orange", prompt: "" },
  ]

  const birdState = loading ? "thinking" : connected ? "idle" : "error"

  const handleQuickAction = (action) => {
    if (action.title === "Поиск") { setActiveTab("search"); return }
    setInput(action.prompt); inputRef.current?.focus()
  }

  const handleCanvasAction = (action, card) => {
    if (card.type === "estimate" && (action === "edit" || action === "export")) {
      setEstimateEditor(card.data)
    }
  }

  return (
    <ErrorBoundary>
      <div className="app">
        <Sidebar
          sidebar={sidebar}
          setSidebar={setSidebar}
          birdState={birdState}
          activeTab={activeTab}
          setActiveTab={setActiveTab}
          clusterStatus={clusterStatus}
          conversations={conversations}
          conversationId={conversationId}
          loadConversation={loadConversation}
          deleteConversation={deleteConversation}
          providers={providers}
          selectedProvider={selectedProvider}
          setSelectedProvider={setSelectedProvider}
          theme={theme}
          setTheme={setTheme}
          connected={connected}
          onNewChat={() => { setMessages([]); setConversationId(null); setActiveTab("chat") }}
        />

        <div className="main-content">
          <header className="header">
            <div className="header-left">
              <button className="header-btn mobile-menu" onClick={() => setSidebar(!sidebar)}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/>
                </svg>
              </button>
              <div>
                <div className="header-title">Kolibri AI</div>
                <div className="header-subtitle">
                  {clusterStatus ? (
                    <span className="header-cluster">
                      <span className="pulse-dot" />
                      {clusterStatus.online_nodes} узлов · {clusterStatus.free_ram_gb} GB RAM
                    </span>
                  ) : "Загрузка..."}
                </div>
              </div>
            </div>
            <div className="header-right">
              <motion.button className="header-btn" onClick={fetchCluster} title="Обновить"
                whileHover={{ rotate: 90 }} transition={{ duration: 0.2 }}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <polyline points="23,4 23,10 17,10"/><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/>
                </svg>
              </motion.button>
            </div>
          </header>

          <AnimatePresence>
            {globalError && (
              <motion.div className="global-error" initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}
                onClick={() => setGlobalError("")}
                style={{ background: "var(--error)", color: "#fff", padding: "8px 16px", textAlign: "center", cursor: "pointer", fontSize: "13px" }}>
                {globalError} (нажмите чтобы закрыть)
              </motion.div>
            )}
          </AnimatePresence>

          {convLoading && (
            <div style={{ display: "flex", justifyContent: "center", padding: 8 }}>
              <div className="typing-indicator"><span /><span /><span /></div>
            </div>
          )}

          <div className="chat-container">
            <AnimatePresence mode="wait">
              {activeTab === "chat" && (
                <ChatView
                  messages={messages}
                  loading={loading}
                  input={input}
                  setInput={setInput}
                  onSend={sendMessage}
                  quickActions={quickActions}
                  onQuickAction={handleQuickAction}
                  onCanvasAction={handleCanvasAction}
                  messagesRef={messagesRef}
                  inputRef={inputRef}
                />
              )}

              {activeTab === "documents" && (
                <DocumentsView
                  documents={documents}
                  docLoading={docLoading}
                  docError={docError}
                  uploading={uploading}
                  onUpload={handleFileUpload}
                />
              )}

              {activeTab === "cluster" && <ClusterView status={clusterStatus} onRefresh={fetchCluster} />}

              {activeTab === "search" && (
                <SearchView
                  searchQuery={searchQuery}
                  setSearchQuery={setSearchQuery}
                  searchResults={searchResults}
                  searchLoading={searchLoading}
                  onSearch={handleSearch}
                />
              )}
            </AnimatePresence>
          </div>
        </div>
        <KolibriCompanion loading={loading} connected={connected} messagesRef={messagesRef} />
        <BottomSheet
          isOpen={!!estimateEditor}
          onClose={() => setEstimateEditor(null)}
          title={estimateEditor?.title || "Смета"}
        >
          {estimateEditor && (
            <EstimateEditor
              estimate={estimateEditor}
              onClose={() => setEstimateEditor(null)}
              onSave={(data) => {
                setEstimateEditor(null)
              }}
            />
          )}
        </BottomSheet>
      </div>
    </ErrorBoundary>
  )
}
