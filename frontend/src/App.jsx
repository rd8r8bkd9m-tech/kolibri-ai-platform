import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import "./App.css"
import { API_BASE, WS_HOST } from "./config"
import { AppHeader } from "./components/AppHeader"
import { ErrorBoundary } from "./components/ErrorBoundary"
import { ChatWorkspace } from "./components/chat/ChatWorkspace"
import { ControlFab } from "./components/control/ControlFab"
import { ControlPanel } from "./components/control/ControlPanel"
import { LandingShell } from "./components/LandingShell"
import { usePwaStatus } from "./hooks/usePwaStatus"
import { useThemeMode } from "./hooks/useThemeMode"
import { controlPlugins, getControlPlugin } from "./plugins/controlPlugins"

const PRODUCT_TITLE = "Фабрика Колибри"
const FACTORY_STATUS_ENDPOINTS = ["/api/factory/status", "/cluster/status"]

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
  const [routePath, setRoutePath] = useState(() => window.location.pathname)
  const [composerFocused, setComposerFocused] = useState(false)
  const messagesEnd = useRef(null)
  const inputRef = useRef(null)
  const fileInputRef = useRef(null)
  const wsRef = useRef(null)
  const reconnectTimer = useRef(null)
  const { theme, setTheme, resolvedTheme } = useThemeMode()
  const pwaStatus = usePwaStatus()
  const isLanding = routePath === "/" || routePath === ""

  const fetchCluster = useCallback(async () => {
    for (const endpoint of FACTORY_STATUS_ENDPOINTS) {
      try {
        const response = await fetch(`${API_BASE}${endpoint}`)
        if (!response.ok) throw new Error(`Factory status returned ${response.status}`)
        setClusterStatus(await response.json())
        return
      } catch {
        // Try the read-only cluster alias if the primary status route is unavailable.
      }
    }
    setClusterStatus(null)
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
    const handlePopState = () => setRoutePath(window.location.pathname)
    window.addEventListener("popstate", handlePopState)
    return () => window.removeEventListener("popstate", handlePopState)
  }, [])

  useEffect(() => {
    window.dispatchEvent(new Event(connected ? "network:online" : "network:offline"))
  }, [connected])

  useEffect(() => {
    if (isLanding) return
    messagesEnd.current?.scrollIntoView({ behavior: "smooth" })
  }, [isLanding, messages])

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

  const openApp = useCallback(() => {
    if (window.location.pathname !== "/app") {
      window.history.pushState({}, "", "/app")
      setRoutePath("/app")
    }
    window.setTimeout(() => inputRef.current?.focus(), 0)
  }, [])

  const handlePrompt = useCallback((prompt) => {
    setInput(prompt)
    inputRef.current?.focus()
  }, [])

  const handleComposerFocus = useCallback(() => {
    setComposerFocused(true)
    window.dispatchEvent(new Event("chat:focus"))
  }, [])

  const handleComposerBlur = useCallback(() => {
    setComposerFocused(false)
    window.dispatchEvent(new Event("chat:blur"))
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
    window.dispatchEvent(new Event("chat:send"))

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

  const birdState = !connected ? "offline" : loading ? "thinking" : composerFocused || input.trim() ? "listening" : "idle"
  const chatProps = {
    messages,
    messagesEndRef: messagesEnd,
    inputRef,
    input,
    loading,
    onInputChange: setInput,
    onSend: sendMessage,
    onPrompt: handlePrompt,
    onControl: openControl,
    onFocus: handleComposerFocus,
    onBlur: handleComposerBlur,
  }

  return (
    <ErrorBoundary>
      <div className={`app chat-first ${isLanding ? "landing-shell" : "app-shell"}`}>
        {isLanding ? (
          <LandingShell
            productTitle={PRODUCT_TITLE}
            birdState={birdState}
            clusterStatus={clusterStatus}
            providers={providers}
            selectedProvider={selectedProvider}
            onProviderChange={setSelectedProvider}
            onOpenSettings={() => openControl("settings")}
            onOpenApp={openApp}
            onOpenControl={openControl}
            pwaStatus={pwaStatus}
            chatProps={{ ...chatProps, messagesEndRef: null }}
          />
        ) : (
          <div className="main-content">
            <AppHeader
              productTitle={PRODUCT_TITLE}
              birdState={birdState}
              clusterStatus={clusterStatus}
              providers={providers}
              selectedProvider={selectedProvider}
              onProviderChange={setSelectedProvider}
              onOpenSettings={() => openControl("settings")}
            />
            <ChatWorkspace {...chatProps} />
          </div>
        )}
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
