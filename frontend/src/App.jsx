import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import "./App.css"
import { API_BASE, WS_HOST } from "./config"
import { AppHeader } from "./components/AppHeader"
import { ErrorBoundary } from "./components/ErrorBoundary"
import { ChatWorkspace } from "./components/chat/ChatWorkspace"
import { ControlFab } from "./components/control/ControlFab"
import { ControlPanel } from "./components/control/ControlPanel"
import { usePwaStatus } from "./hooks/usePwaStatus"
import { useThemeMode } from "./hooks/useThemeMode"
import { controlPlugins, getControlPlugin } from "./plugins/controlPlugins"

export default function App() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState("")
  const [loading, setLoading] = useState(false)
  const [connected, setConnected] = useState(false)
  const [providers, setProviders] = useState([])
  const [selectedProvider, setSelectedProvider] = useState("mimo")
  const [documents, setDocuments] = useState([])
  const [docLoading, setDocLoading] = useState(false)
  const [docError, setDocError] = useState("")
  const [uploading, setUploading] = useState(false)
  const [clusterStatus, setClusterStatus] = useState(null)
  const [searchQuery, setSearchQuery] = useState("")
  const [searchResults, setSearchResults] = useState([])
  const [searchLoading, setSearchLoading] = useState(false)
  const [controlOpen, setControlOpen] = useState(false)
  const [activeControl, setActiveControl] = useState("billing")
  const [billingPlans, setBillingPlans] = useState({ configured: false, plans: [] })
  const [billingForm, setBillingForm] = useState({ plan_id: "team", email: "", name: "", company: "", phone: "" })
  const [billingLoading, setBillingLoading] = useState(false)
  const [billingMessage, setBillingMessage] = useState("")
  const messagesEnd = useRef(null)
  const inputRef = useRef(null)
  const fileInputRef = useRef(null)
  const wsRef = useRef(null)
  const reconnectTimer = useRef(null)
  const { theme, setTheme, resolvedTheme } = useThemeMode()
  const pwaStatus = usePwaStatus()

  const fetchCluster = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE}/api/factory/status`)
      setClusterStatus(await response.json())
    } catch {
      setClusterStatus(null)
    }
  }, [])

  const fetchDocuments = useCallback(async () => {
    setDocLoading(true)
    setDocError("")
    try {
      const response = await fetch(`${API_BASE}/api/knowledge`)
      const data = await response.json()
      setDocuments(data.documents || data.items || [])
    } catch {
      setDocError("Не удалось загрузить документы")
    }
    setDocLoading(false)
  }, [])

  const fetchBillingPlans = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE}/api/billing/plans`)
      const data = await response.json()
      setBillingPlans(data)
      if (data.plans?.length && !data.plans.some(plan => plan.id === billingForm.plan_id)) {
        setBillingForm(prev => ({ ...prev, plan_id: data.plans[0].id }))
      }
    } catch {
      setBillingPlans(prev => prev)
    }
  }, [billingForm.plan_id])

  const connectWS = useCallback(() => {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:"
    let socket
    try {
      socket = new WebSocket(`${proto}//${WS_HOST}/ws/chat`)
    } catch {
      return
    }
    socket.onopen = () => setConnected(true)
    socket.onclose = () => {
      setConnected(false)
      reconnectTimer.current = setTimeout(connectWS, 3000)
    }
    socket.onmessage = (event) => {
      const data = JSON.parse(event.data)
      setMessages(prev => {
        const next = [...prev]
        const last = next[next.length - 1]
        if (last && last.role === "assistant" && last.streaming) {
          last.content = data.response || data.content || ""
          last.provider = data.provider
          last.streaming = false
        }
        return [...next]
      })
      setLoading(false)
    }
    wsRef.current = socket
  }, [])

  useEffect(() => {
    fetch(`${API_BASE}/api/providers`).then(r => r.json()).then(setProviders).catch(() => {})
    connectWS()
    fetchCluster()
    fetchBillingPlans()
    const clusterTimer = setInterval(fetchCluster, 15000)
    return () => {
      wsRef.current?.close()
      clearInterval(clusterTimer)
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
    }
  }, [connectWS, fetchCluster, fetchBillingPlans])

  useEffect(() => {
    messagesEnd.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  useEffect(() => {
    if (controlOpen && activeControl === "docs") fetchDocuments()
  }, [controlOpen, activeControl, fetchDocuments])

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const payment = params.get("payment")
    if (!payment) return
    setMessages([{
      role: "assistant",
      content: payment === "success"
        ? "Оплата принята. Подписка активируется после подтверждения Т-Банка."
        : "Платёж не завершён. Откройте Контрол и попробуйте ещё раз.",
      timestamp: Date.now(),
    }])
    window.history.replaceState({}, "", window.location.pathname)
  }, [])

  const openControl = useCallback((tab = "billing") => {
    setActiveControl(tab)
    setControlOpen(true)
  }, [])

  const handlePrompt = useCallback((prompt) => {
    setInput(prompt)
    inputRef.current?.focus()
  }, [])

  const handleFileUpload = async (event) => {
    const file = event.target.files?.[0]
    if (!file) return
    setUploading(true)
    try {
      const body = new FormData()
      body.append("file", file)
      await fetch(`${API_BASE}/api/knowledge/upload`, { method: "POST", body })
      await fetchDocuments()
    } catch {
      setDocError("Ошибка загрузки")
    }
    setUploading(false)
  }

  const sendMessage = async () => {
    if (!input.trim() || loading) return
    const userMessage = { role: "user", content: input, timestamp: Date.now() }
    const nextMessages = [...messages, userMessage]
    setMessages([...nextMessages, { role: "assistant", content: "", streaming: true, provider: "", timestamp: Date.now() }])
    setInput("")
    setLoading(true)

    const socket = wsRef.current
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({
        messages: nextMessages.map(message => ({ role: message.role, content: message.content })),
        provider: selectedProvider,
      }))
      return
    }

    try {
      const response = await fetch(`${API_BASE}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: nextMessages, provider: selectedProvider }),
      })
      const data = await response.json()
      setMessages([...nextMessages, { role: "assistant", content: data.response, provider: data.provider, timestamp: Date.now() }])
    } catch {
      setMessages([...nextMessages, { role: "assistant", content: "Ошибка подключения к серверу.", timestamp: Date.now() }])
    }
    setLoading(false)
  }

  const handleSearch = async () => {
    if (!searchQuery.trim()) return
    setSearchLoading(true)
    try {
      const response = await fetch(`${API_BASE}/api/knowledge/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: searchQuery, limit: 5 }),
      })
      const data = await response.json()
      setSearchResults(data.results || [])
    } catch {
      setSearchResults([])
    }
    setSearchLoading(false)
  }

  const handleCheckout = async (event) => {
    event.preventDefault()
    setBillingLoading(true)
    setBillingMessage("")
    try {
      const response = await fetch(`${API_BASE}/api/billing/checkout`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(billingForm),
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || "Ошибка оплаты")
      if (data.payment_url) {
        window.location.href = data.payment_url
        return
      }
      setBillingMessage(data.message || "Заявка сохранена")
    } catch (error) {
      setBillingMessage(error.message || "Не удалось создать платёж")
    }
    setBillingLoading(false)
  }

  const pluginContext = useMemo(() => ({
    billing: {
      plans: billingPlans,
      form: billingForm,
      setForm: setBillingForm,
      loading: billingLoading,
      message: billingMessage,
      onSubmit: handleCheckout,
    },
    documents: {
      items: documents,
      loading: docLoading,
      error: docError,
      uploading,
      fileInputRef,
      onUpload: handleFileUpload,
    },
    search: {
      query: searchQuery,
      setQuery: setSearchQuery,
      results: searchResults,
      loading: searchLoading,
      onSearch: handleSearch,
    },
    cluster: {
      status: clusterStatus,
      onRefresh: fetchCluster,
    },
    settings: {
      theme,
      setTheme,
      resolvedTheme,
      pwaStatus,
    },
  }), [
    billingForm,
    billingLoading,
    billingMessage,
    billingPlans,
    clusterStatus,
    docError,
    docLoading,
    documents,
    pwaStatus,
    resolvedTheme,
    searchLoading,
    searchQuery,
    searchResults,
    theme,
    uploading,
  ])

  const activePlugin = getControlPlugin(activeControl)

  const birdState = loading ? "thinking" : connected ? "idle" : "error"

  return (
    <ErrorBoundary>
      <div className="app chat-first">
        <div className="main-content">
          <AppHeader
            birdState={birdState}
            clusterStatus={clusterStatus}
            providers={providers}
            selectedProvider={selectedProvider}
            onProviderChange={setSelectedProvider}
            onOpenSettings={() => openControl("settings")}
          />
          <ChatWorkspace
            messages={messages}
            messagesEndRef={messagesEnd}
            inputRef={inputRef}
            input={input}
            loading={loading}
            onInputChange={setInput}
            onSend={sendMessage}
            onPrompt={handlePrompt}
            onControl={openControl}
          />
        </div>
        <ControlFab open={controlOpen} onClick={() => setControlOpen(prev => !prev)} />
        <ControlPanel
          open={controlOpen}
          active={activeControl}
          setActive={setActiveControl}
          onClose={() => setControlOpen(false)}
          plugins={controlPlugins}
        >
          {activePlugin.render(pluginContext)}
        </ControlPanel>
      </div>
    </ErrorBoundary>
  )
}
