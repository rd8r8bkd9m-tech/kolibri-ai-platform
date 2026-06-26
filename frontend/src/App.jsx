import { useState, useEffect, useRef, useCallback, Component } from "react"
import { motion, AnimatePresence } from "framer-motion"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import "./App.css"
import { KolibriBird } from "./components/KolibriBird"

const API_BASE = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1"
  ? `http://${window.location.hostname}:8000`
  : ""

class ErrorBoundary extends Component {
  constructor(props) { super(props); this.state = { error: null } }
  static getDerivedStateFromError(error) { return { error } }
  render() {
    if (this.state.error) {
      return (
        <div className="error-boundary">
          <KolibriBird size={64} state="error" />
          <h2>Что-то пошло не так</h2>
          <p>{this.state.error.message}</p>
          <button className="upload-btn" onClick={() => { this.setState({ error: null }); window.location.reload() }}>
            Перезагрузить
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

function parseThinking(text) {
  const match = text.match(/<thinking>([\s\S]*?)<\/thinking>/)
  if (match) return { thinking: match[1].trim(), content: text.replace(/<thinking>[\s\S]*?<\/thinking>/, "").trim() }
  return { thinking: null, content: text }
}

function ThinkingBlock({ text, isStreaming }) {
  const [expanded, setExpanded] = useState(isStreaming)
  useEffect(() => { if (isStreaming) setExpanded(true) }, [isStreaming])
  useEffect(() => {
    if (!isStreaming && text) { const t = setTimeout(() => setExpanded(false), 2000); return () => clearTimeout(t) }
  }, [isStreaming, text])
  if (!text) return null
  return (
    <motion.div className="thinking-block" onClick={() => setExpanded(!expanded)}
      initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} transition={{ duration: 0.3 }}>
      <div className="thinking-header">
        {isStreaming && <div className="spinner"></div>}
        <span>{isStreaming ? "Думаю..." : "Рассуждения"}</span>
        <span style={{ marginLeft: "auto", fontSize: "10px" }}>{expanded ? "▲" : "▼"}</span>
      </div>
      {expanded && <div className="thinking-content"><ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown></div>}
    </motion.div>
  )
}

function Skeleton({ className }) {
  return <div className={`skeleton ${className || ""}`} />
}

function ClusterView({ status, onRefresh }) {
  if (!status) return (
    <div className="documents-panel">
      <div className="skeleton-grid">
        {[1,2,3].map(i => <Skeleton key={i} className="skeleton-card" />)}
      </div>
    </div>
  )
  
  const nodeEntries = Array.isArray(status.nodes) ? status.nodes.map(node => [node.node_id || node.id || node.hostname, node]) : Object.entries(status.nodes || {})

  const NodeIcon = ({ role }) => {
    const paths = {
      training: "M2 3h6a4 4 0 014 4v14a3 3 0 00-3-3H2zM22 3h-6a4 4 0 00-4 4v14a3 3 0 013-3h7z",
      "api-gateway": "M12 2a10 10 0 100 20 10 10 0 000-20zM2 12h20M12 2a15 15 0 014 10 15 15 0 01-4 10 15 15 0 01-4-10A15 15 0 0112 2z",
      rag: "M4 19.5A2.5 2.5 0 016.5 17H20zM6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z",
      agent: "M12 2a2 2 0 100 4 2 2 0 000-4zM6 11h12a2 2 0 012 2v7a2 2 0 01-2 2H6a2 2 0 01-2-2v-7a2 2 0 012-2z",
      inference: "M13 2L3 14h9l-1 8 10-12h-9l1-8z",
    }
    const d = paths[role] || paths["api-gateway"]
    return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d={d}/></svg>
  }
  
  return (
    <motion.div key="cluster" className="documents-panel" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
      <div className="documents-header">
        <h2>Сеть Kolibri</h2>
        <button className="refresh-btn" onClick={onRefresh}>
          <motion.svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
            whileHover={{ rotate: 180 }} transition={{ duration: 0.3 }}>
            <polyline points="23,4 23,10 17,10"/><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/>
          </motion.svg>
        </button>
      </div>
      
      <div className="cluster-stats">
        {[
          { label: "Узлов онлайн", value: `${status.online_nodes}/${status.total_nodes}`, icon: <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71"/></svg>, color: "var(--accent)" },
          { label: "RAM свободно", value: `${status.free_ram_gb} GB`, icon: <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="2" y="6" width="20" height="12" rx="2"/><path d="M6 12h4"/><path d="M14 12h4"/></svg>, color: "var(--success)" },
          { label: "CPU средний", value: `${status.avg_cpu_percent}%`, icon: <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><path d="M15 2v2"/><path d="M15 20v2"/><path d="M2 15h2"/><path d="M2 9h2"/><path d="M20 15h2"/><path d="M20 9h2"/><path d="M9 2v2"/><path d="M9 20v2"/></svg>, color: "var(--text-primary)" },
          { label: "Задач в очереди", value: status.queue_size || 0, icon: <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M16 4h2a2 2 0 012 2v14a2 2 0 01-2 2H6a2 2 0 01-2-2V6a2 2 0 012-2h2"/><rect x="8" y="2" width="8" height="4" rx="1"/></svg>, color: "var(--warning)" },
        ].map((s, i) => (
          <motion.div key={s.label} className="stat-card"
            initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: i * 0.08, type: "spring", stiffness: 200 }}>
            <div className="stat-icon">{s.icon}</div>
            <div className="stat-value" style={{ color: s.color }}>{s.value}</div>
            <div className="stat-label">{s.label}</div>
          </motion.div>
        ))}
      </div>
      
      <div className="doc-list">
        {nodeEntries.map(([name, node], i) => (
          <motion.div key={name} className="doc-item node-card"
            initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.3 + i * 0.06, type: "spring", stiffness: 150 }}
            whileHover={{ scale: 1.01, x: 4 }}>
            <div className="doc-icon" style={{
              background: node.status === "online" ? "rgba(16,185,129,0.1)" : "rgba(239,68,68,0.1)",
              color: node.status === "online" ? "var(--success)" : "var(--error)"
            }}>
              <NodeIcon role={node.role} />
            </div>
            <div className="doc-info">
              <div className="doc-name" style={{ textTransform: "capitalize" }}>{name}</div>
              <div className="doc-meta">{node.role} · {node.hostname || node.ip || node.agent_id || "internal"}</div>
            </div>
            <div style={{ textAlign: "right" }}>
              <div style={{ fontSize: "13px", fontWeight: "600" }}>CPU {node.cpu == null ? "n/a" : node.cpu}</div>
              <div className="ram-bar">
                <div className="ram-bar-fill" style={{ width: `${node.ram_total_gb ? Math.min(100, ((node.ram_total_gb - node.ram_available_gb) / node.ram_total_gb) * 100) : Math.min(100, (parseFloat(node.ram || 0) / 16) * 100)}%` }} />
              </div>
              <div style={{ fontSize: "11px", color: "var(--text-muted)" }}>{node.ram || `${node.ram_available_gb || 0}/${node.ram_total_gb || 0} GB`}</div>
            </div>
          </motion.div>
        ))}
      </div>
    </motion.div>
  )
}

export default function App() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState("")
  const [loading, setLoading] = useState(false)
  const [ws, setWs] = useState(null)
  const [connected, setConnected] = useState(false)
  const [providers, setProviders] = useState([])
  const [selectedProvider, setSelectedProvider] = useState("mimo")
  const [sidebar, setSidebar] = useState(false)
  const [theme, setTheme] = useState(() => localStorage.getItem("kolibri-theme") || "dark")
  const [activeTab, setActiveTab] = useState("chat")
  const [documents, setDocuments] = useState([])
  const [docLoading, setDocLoading] = useState(false)
  const [docError, setDocError] = useState("")
  const [uploading, setUploading] = useState(false)
  const [clusterStatus, setClusterStatus] = useState(null)
  const [searchQuery, setSearchQuery] = useState("")
  const [searchResults, setSearchResults] = useState([])
  const [searchLoading, setSearchLoading] = useState(false)
  const messagesEnd = useRef(null)
  const inputRef = useRef(null)
  const fileInputRef = useRef(null)

  useEffect(() => {
    const root = document.documentElement
    root.classList.remove("theme-dark", "theme-light")
    root.classList.add(theme === "dark" ? "theme-dark" : "theme-light")
    localStorage.setItem("kolibri-theme", theme)
    document.querySelector('meta[name="theme-color"]')?.setAttribute("content", theme === "dark" ? "#0a0a0f" : "#f0f4f8")
  }, [theme])

  useEffect(() => {
    fetch(`${API_BASE}/api/providers`).then(r => r.json()).then(setProviders).catch(() => {})
    connectWS()
    fetchCluster()
    const ci = setInterval(fetchCluster, 15000)
    return () => { if (ws) ws.close(); clearInterval(ci) }
  }, [])

  useEffect(() => { messagesEnd.current?.scrollIntoView({ behavior: "smooth" }) }, [messages])

  const fetchCluster = async () => {
    try {
      const r = await fetch(`${API_BASE}/api/factory/status`)
      setClusterStatus(await r.json())
    } catch {}
  }

  const fetchDocuments = async () => {
    setDocLoading(true); setDocError("")
    try {
      const r = await fetch(`${API_BASE}/api/knowledge`)
      const d = await r.json()
      setDocuments(d.documents || d.items || [])
    } catch { setDocError("Не удалось загрузить документы") }
    setDocLoading(false)
  }

  useEffect(() => { if (activeTab === "documents") fetchDocuments() }, [activeTab])

  const handleFileUpload = async (e) => {
    const file = e.target.files?.[0]; if (!file) return
    setUploading(true)
    try {
      const fd = new FormData(); fd.append("file", file)
      await fetch(`${API_BASE}/api/knowledge/upload`, { method: "POST", body: fd })
      await fetchDocuments()
    } catch { setDocError("Ошибка загрузки") }
    setUploading(false)
  }

  const connectWS = useCallback(() => {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:"
    let socket
    try { socket = new WebSocket(`${proto}//${window.location.hostname}:8000/ws/chat`) } catch { return }
    socket.onopen = () => setConnected(true)
    socket.onclose = () => { setConnected(false); setTimeout(connectWS, 3000) }
    socket.onmessage = (e) => {
      const data = JSON.parse(e.data)
      setMessages(prev => {
        const n = [...prev]
        const last = n[n.length - 1]
        if (last && last.role === "assistant" && last.streaming) {
          last.content = data.response || data.content || ""
          last.provider = data.provider
          last.streaming = false
        }
        return [...n]
      })
      setLoading(false)
    }
    setWs(socket)
  }, [])

  const sendMessage = async () => {
    if (!input.trim() || loading) return
    const userMsg = { role: "user", content: input, timestamp: Date.now() }
    const newMsgs = [...messages, userMsg]
    setMessages(newMsgs); setInput(""); setLoading(true)
    setMessages([...newMsgs, { role: "assistant", content: "", streaming: true, provider: "", timestamp: Date.now() }])
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ messages: newMsgs.map(m => ({ role: m.role, content: m.content })), provider: selectedProvider }))
    } else {
      try {
        const r = await fetch(`${API_BASE}/api/chat`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ messages: newMsgs, provider: selectedProvider }) })
        const d = await r.json()
        setMessages([...newMsgs, { role: "assistant", content: d.response, provider: d.provider, timestamp: Date.now() }])
      } catch { setMessages([...newMsgs, { role: "assistant", content: "Ошибка подключения к серверу.", timestamp: Date.now() }]) }
      setLoading(false)
    }
  }

  const handleSearch = async () => {
    if (!searchQuery.trim()) return
    setSearchLoading(true)
    try {
      const r = await fetch(`${API_BASE}/rag/search`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ query: searchQuery, limit: 5 }) })
      const d = await r.json()
      setSearchResults(d.results || [])
    } catch { setSearchResults([]) }
    setSearchLoading(false)
  }

  const handleKeyDown = (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage() } }

  const quickActions = [
    { icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>, title: "Чат с AI", desc: "Задайте вопрос", color: "blue", prompt: "" },
    { icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14,2 14,8 20,8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>, title: "Смета", desc: "AI-генерация сметы", color: "purple", prompt: "Создай строительную смету для " },
    { icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 002 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0022 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg>, title: "Документы", desc: "Пакет документов", color: "green", prompt: "Создай полный пакет документов для " },
    { id: "search", icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>, title: "Поиск", desc: "База знаний", color: "orange", prompt: "" },
  ]

  const birdState = loading ? "thinking" : connected ? "idle" : "error"

  return (
    <ErrorBoundary>
      <div className="app">
        <div className={`sidebar-overlay ${sidebar ? "open" : ""}`} onClick={() => setSidebar(false)} />

        <aside className={`sidebar ${sidebar ? "open" : ""}`}>
          <div className="sidebar-header">
            <div className="sidebar-logo">
              <KolibriBird size={36} state={birdState} />
              <span className="sidebar-logo-text">Kolibri</span>
              <span className="sidebar-logo-badge">AI</span>
            </div>
            <motion.button className="new-chat-btn" onClick={() => { setMessages([]); setActiveTab("chat") }}
              whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
              </svg>
              Новый чат
            </motion.button>
          </div>

          <nav className="sidebar-nav">
            {[
              { id: "chat", label: "Чат", icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg> },
              { id: "documents", label: "Документы", icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14,2 14,8 20,8"/></svg> },
              { id: "search", label: "Поиск", icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg> },
              { id: "cluster", label: "Сеть", icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="2" y="2" width="6" height="6" rx="1"/><rect x="16" y="2" width="6" height="6" rx="1"/><rect x="9" y="16" width="6" height="6" rx="1"/><path d="M5 8v3a2 2 0 002 2h10a2 2 0 002-2V8"/></svg> },
            ].map(item => (
              <motion.button key={item.id} className={`sidebar-nav-item ${activeTab === item.id ? "active" : ""}`}
                onClick={() => { setActiveTab(item.id); setSidebar(false) }}
                whileHover={{ x: 2 }} whileTap={{ scale: 0.98 }}>
                {item.icon}{item.label}
                {item.id === "cluster" && clusterStatus && (
                  <span className="nav-badge">{clusterStatus.online_nodes}</span>
                )}
              </motion.button>
            ))}
          </nav>

          <div className="sidebar-section">
            <div className="sidebar-label">Модель</div>
            <select className="sidebar-select" value={selectedProvider} onChange={e => setSelectedProvider(e.target.value)}>
              {providers.filter(p => p.available).map(p => <option key={p.name} value={p.name}>{p.name}</option>)}
              {providers.length === 0 && <option value="mimo">mimo-auto</option>}
            </select>
          </div>

          <div className="sidebar-section">
            <div className="sidebar-label">Тема</div>
            <motion.div className="theme-switch" onClick={() => setTheme(theme === "light" ? "dark" : "light")}
              whileTap={{ scale: 0.98 }}>
              <span className="theme-switch-label">{theme === "light" ? "Светлая" : "Тёмная"}</span>
              <div className={`theme-switch-toggle ${theme === "dark" ? "active" : ""}`}></div>
            </motion.div>
          </div>

          <div className="sidebar-footer">
            <div className="connection-status">
              <motion.div className={`connection-dot ${connected ? "connected" : ""}`}
                animate={connected ? { scale: [1, 1.3, 1] } : {}}
                transition={{ duration: 2, repeat: Infinity }} />
              {connected ? "Фабрика онлайн" : "Связь с фабрикой потеряна"}
            </div>
          </div>
        </aside>

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

          <div className="chat-container">
            <AnimatePresence mode="wait">
              {activeTab === "chat" && (
                <motion.div key="chat" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }}
                  transition={{ duration: 0.2 }} style={{ display: "flex", flexDirection: "column", flex: 1 }}>
                  <div className="messages">
                    {messages.length === 0 && (
                      <motion.div className="welcome" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.6 }}>
                        <motion.div initial={{ scale: 0.8, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
                          transition={{ type: "spring", stiffness: 200, delay: 0.1 }}>
                          <KolibriBird size={90} state="idle" />
                        </motion.div>
                        <motion.h1 className="welcome-title" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
                          transition={{ delay: 0.3 }}>Kolibri AI</motion.h1>
                        <motion.p className="welcome-subtitle" initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                          transition={{ delay: 0.4 }}>
                          Фабрика Колибри · {clusterStatus ? `${clusterStatus.online_nodes}/${clusterStatus.total_nodes} узлов · ${clusterStatus.total_ram_gb} GB RAM` : "загрузка"}
                        </motion.p>
                        <div className="quick-actions">
                          {quickActions.map((a, i) => (
                            <motion.button key={a.title} className="quick-action"
                              initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
                              transition={{ delay: 0.5 + i * 0.08, type: "spring", stiffness: 200 }}
                              whileHover={{ scale: 1.03, y: -3 }} whileTap={{ scale: 0.97 }}
                              onClick={() => {
                                if (a.id === "search") { setActiveTab("search"); return }
                                setInput(a.prompt); inputRef.current?.focus()
                              }}>
                              <div className={`quick-action-icon ${a.color}`}>{a.icon}</div>
                              <div className="quick-action-text">
                                <div className="quick-action-title">{a.title}</div>
                                <div className="quick-action-desc">{a.desc}</div>
                              </div>
                            </motion.button>
                          ))}
                        </div>
                      </motion.div>
                    )}
                    {messages.map((msg, i) => {
                      const { thinking, content } = msg.role === "assistant" ? parseThinking(msg.content || "") : { thinking: null, content: msg.content }
                      return (
                        <motion.div key={i} className={`message ${msg.role}`}
                          initial={{ opacity: 0, y: 10, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }}
                          transition={{ duration: 0.25, type: "spring", stiffness: 200 }}>
                          <div className={`message-avatar ${msg.role}`}>
                            {msg.role === "assistant" ? <KolibriBird size={20} state={msg.streaming ? "thinking" : "happy"} /> : "U"}
                          </div>
                          <div className="message-bubble">
                            {msg.role === "assistant" && <ThinkingBlock text={thinking} isStreaming={msg.streaming} />}
                            {msg.role === "assistant" ? (
                              <ReactMarkdown remarkPlugins={[remarkGfm]}>{content || (msg.streaming ? "..." : "")}</ReactMarkdown>
                            ) : <p>{msg.content}</p>}
                            {msg.provider && msg.role === "assistant" && (
                              <motion.div className="provider-badge" initial={{ opacity: 0, scale: 0.8 }} animate={{ opacity: 1, scale: 1 }}>
                                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg> {msg.provider}
                              </motion.div>
                            )}
                          </div>
                        </motion.div>
                      )
                    })}
                    {loading && messages[messages.length-1]?.streaming && (
                      <motion.div className="message assistant" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                        <div className="message-avatar assistant"><KolibriBird size={20} state="thinking" /></div>
                        <div className="message-bubble typing-indicator">
                          <span></span><span></span><span></span>
                        </div>
                      </motion.div>
                    )}
                    <div ref={messagesEnd} />
                  </div>

                  <div className="input-area">
                    <div className="input-wrapper">
                      <textarea ref={inputRef} value={input} onChange={e => setInput(e.target.value)} onKeyDown={handleKeyDown}
                        placeholder="Спросите что угодно..." rows={1} disabled={loading}
                        onInput={e => { e.target.style.height = "auto"; e.target.style.height = Math.min(e.target.scrollHeight, 120) + "px" }} />
                      <motion.button onClick={sendMessage} disabled={loading || !input.trim()} className="send-btn"
                        whileHover={{ scale: 1.08 }} whileTap={{ scale: 0.92 }}>
                        {loading ? (
                          <motion.svg className="spinner-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"
                            animate={{ rotate: 360 }} transition={{ duration: 1, repeat: Infinity, ease: "linear" }}>
                            <path d="M21 12a9 9 0 11-6.219-8.56"/>
                          </motion.svg>
                        ) : (
                          <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>
                        )}
                      </motion.button>
                    </div>
                  </div>
                </motion.div>
              )}

              {activeTab === "documents" && (
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
              )}

              {activeTab === "cluster" && <ClusterView status={clusterStatus} onRefresh={fetchCluster} />}

              {activeTab === "search" && (
                <motion.div key="search" className="documents-panel" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
                  <div className="documents-header"><h2>Поиск</h2></div>
                  <div style={{ marginBottom: "20px" }}>
                    <div className="input-wrapper" style={{ maxWidth: "600px" }}>
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted)" strokeWidth="2" style={{ flexShrink: 0 }}>
                        <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
                      </svg>
                      <input type="text" value={searchQuery} onChange={e => setSearchQuery(e.target.value)}
                        onKeyDown={e => e.key === "Enter" && handleSearch()}
                        placeholder="Поиск по базе знаний..."
                        style={{ flex:1, border:"none", background:"transparent", color:"var(--text-primary)", fontSize:"14px", fontFamily:"var(--font-ui)", outline:"none", padding:"8px 0" }} />
                      <motion.button className="send-btn" style={{ width:"36px", height:"36px" }} onClick={handleSearch}
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
              )}
            </AnimatePresence>
          </div>
        </div>
      </div>
    </ErrorBoundary>
  )
}
