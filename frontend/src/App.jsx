import { Component, useEffect, useMemo, useRef, useState } from "react"
import { AnimatePresence, motion } from "framer-motion"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import "./App.css"
import { KolibriBird } from "./components/KolibriBird"

const IS_LOCAL = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1"
const API_BASE = IS_LOCAL ? `http://${window.location.hostname}:8000` : ""

const MODES = [
  { id: "fast", label: "Быстро", hint: "короткий ответ" },
  { id: "deep", label: "Глубже", hint: "структура и шаги" },
  { id: "search", label: "Поиск", hint: "база знаний" },
]

const DIRECTIONS = [
  {
    id: "construction",
    title: "Сметы и стройка",
    label: "Пилот",
    description: "Профессиональный пилот для черновой оценки работ, материалов и рисков.",
    prompt: "Нужна строительная смета: объект, площадь, регион, перечень работ, качество материалов.",
    keywords: ["смет", "строй", "ремонт", "материал", "объект", "кровл", "фундамент", "м2", "площад"],
  },
  {
    id: "documents",
    title: "Документы",
    label: "Инструмент",
    description: "Собрать ТЗ, договор, письмо, регламент или пакет согласования.",
    prompt: "Помоги собрать документ: цель, адресат, исходные данные, формат результата.",
    keywords: ["документ", "договор", "тз", "акт", "письм", "регламент", "таблиц", "pdf"],
  },
  {
    id: "business",
    title: "Бизнес-направление",
    label: "Направление",
    description: "Разобрать задачу, рынок, предложение, план запуска или продажи.",
    prompt: "Разбери бизнес-задачу: продукт, клиент, ограничение, желаемый результат.",
    keywords: ["продаж", "клиент", "рынок", "маркет", "выруч", "воронк", "офер", "запуск"],
  },
  {
    id: "engineering",
    title: "Техническая работа",
    label: "Направление",
    description: "План, отладка, архитектура, интеграция, проверка гипотез.",
    prompt: "Помоги с технической задачей: система, ошибка, ожидаемое поведение, ограничения.",
    keywords: ["код", "api", "ошиб", "сервер", "интеграц", "архитект", "лог", "deploy", "ci"],
  },
  {
    id: "operations",
    title: "Операции",
    label: "Направление",
    description: "Сводки, контроль статуса, риски, очереди, следующие действия.",
    prompt: "Собери операционную сводку: контекст, статус, блокеры, следующий шаг.",
    keywords: ["статус", "сводк", "очеред", "план", "риск", "операц", "контроль", "срок"],
  },
]

const STARTER_MESSAGES = [
  {
    role: "assistant",
    content:
      "Я начну с разговора, а рабочие направления открою по смыслу запроса. Опишите задачу обычными словами: смета, документ, поиск, запуск, техническая проблема или операционный статус.",
    createdAt: Date.now(),
    local: true,
  },
]

class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  render() {
    if (this.state.error) {
      return (
        <div className="error-boundary">
          <KolibriBird size={76} state="error" />
          <h1>Интерфейс остановился</h1>
          <p>{this.state.error.message}</p>
          <button className="primary-action" onClick={() => window.location.reload()}>
            Перезагрузить
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

function Icon({ name }) {
  const paths = {
    menu: "M4 6h16M4 12h16M4 18h16",
    plus: "M12 5v14M5 12h14",
    send: "M3 20l18-8L3 4v6l11 2-11 2v6z",
    search: "M11 19a8 8 0 100-16 8 8 0 000 16zM21 21l-4.35-4.35",
    bolt: "M13 2L4 14h7l-1 8 10-12h-7l1-8z",
    layers: "M12 2l9 5-9 5-9-5 9-5zM3 12l9 5 9-5M3 17l9 5 9-5",
    file: "M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8zM14 2v6h6M8 13h8M8 17h6",
    shield: "M12 2l8 4v6c0 5-3.4 8.6-8 10-4.6-1.4-8-5-8-10V6l8-4z",
    refresh: "M21 12a9 9 0 11-2.64-6.36M21 3v6h-6",
    spark: "M12 2v5M12 17v5M4.93 4.93l3.54 3.54M15.54 15.54l3.53 3.53M2 12h5M17 12h5M4.93 19.07l3.54-3.53M15.54 8.46l3.53-3.53",
    warning: "M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0zM12 9v4M12 17h.01",
  }

  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" fill={name === "send" ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d={paths[name] || paths.spark} />
    </svg>
  )
}

function inferWorkspace(messages, input) {
  const text = `${messages.map((m) => m.content).join(" ")} ${input}`.toLowerCase()
  const ranked = DIRECTIONS.map((direction) => ({
    ...direction,
    score: direction.keywords.reduce((sum, keyword) => sum + (text.includes(keyword) ? 1 : 0), 0),
  })).sort((a, b) => b.score - a.score)

  const hasSignal = ranked[0]?.score > 0
  const primary = hasSignal ? ranked[0] : DIRECTIONS[0]
  const visible = hasSignal ? ranked.filter((item) => item.score > 0).concat(ranked.filter((item) => item.score === 0)).slice(0, 4) : DIRECTIONS.slice(0, 4)
  const confidence = hasSignal ? Math.min(96, 54 + ranked[0].score * 14) : 36

  return {
    primary,
    visible,
    confidence,
    status: hasSignal ? "По разговору найдено направление" : "Жду первые детали задачи",
  }
}

function buildFailureMessage(result, action) {
  if (result.status === 401 || result.status === 403) {
    return `Не могу выполнить "${action}": backend ответил HTTP ${result.status}. Нужна авторизация или корректная сессия. Ошибка не скрыта: действие остановлено без имитации успеха.`
  }
  if (result.status) {
    return `Не могу выполнить "${action}": backend ответил HTTP ${result.status}. Повторите после восстановления сервиса или проверьте endpoint.`
  }
  return `Не могу выполнить "${action}": ${result.error || "backend недоступен"}. Данные не были подменены локальной заглушкой.`
}

async function safeJsonFetch(path, options = {}) {
  try {
    const response = await fetch(`${API_BASE}${path}`, options)
    let data = null
    const contentType = response.headers.get("content-type") || ""
    if (contentType.includes("application/json")) {
      data = await response.json()
    } else {
      const text = await response.text()
      data = text ? { message: text } : null
    }
    if (!response.ok) return { ok: false, status: response.status, data }
    return { ok: true, status: response.status, data }
  } catch (error) {
    return { ok: false, status: 0, error: error.message }
  }
}

function StatusPill({ backendState }) {
  const className = backendState.kind === "online" ? "online" : backendState.kind === "error" ? "error" : "idle"
  return (
    <span className={`status-pill ${className}`}>
      <span />
      {backendState.label}
    </span>
  )
}

function Message({ message }) {
  const isAssistant = message.role === "assistant"
  return (
    <motion.article
      className={`message ${message.role}`}
      initial={{ opacity: 0, y: 10, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.2 }}
    >
      {isAssistant ? (
        <div className="message-bird">
          <KolibriBird size={34} state={message.state || "calm"} />
        </div>
      ) : null}
      <div className="message-body">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
        {message.meta ? <div className="message-meta">{message.meta}</div> : null}
      </div>
    </motion.article>
  )
}

export default function App() {
  const [messages, setMessages] = useState(STARTER_MESSAGES)
  const [input, setInput] = useState("")
  const [mode, setMode] = useState("fast")
  const [loading, setLoading] = useState(false)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [backendState, setBackendState] = useState({ kind: "idle", label: "Backend не проверен", detail: "Запросов на старте нет" })
  const [providers, setProviders] = useState([])
  const [searchResults, setSearchResults] = useState([])
  const [lastChecked, setLastChecked] = useState("")
  const messagesEnd = useRef(null)
  const inputRef = useRef(null)

  const workspace = useMemo(() => inferWorkspace(messages, input), [messages, input])
  const birdState = loading ? "thinking" : backendState.kind === "error" ? "surprised" : input.trim() ? "listening" : "flying"

  useEffect(() => {
    document.documentElement.classList.remove("theme-dark", "theme-light")
    document.documentElement.classList.add("theme-light")
    document.querySelector('meta[name="theme-color"]')?.setAttribute("content", "#f7fafc")
  }, [])

  useEffect(() => {
    messagesEnd.current?.scrollIntoView({ behavior: "smooth", block: "end" })
  }, [messages, loading])

  const appendAssistant = (content, state = "calm", meta = "") => {
    setMessages((current) => [...current, { role: "assistant", content, state, meta, createdAt: Date.now(), local: true }])
  }

  const checkBackend = async () => {
    setBackendState({ kind: "checking", label: "Проверяю backend", detail: "Запрошен /api/providers" })
    const result = await safeJsonFetch("/api/providers")
    setLastChecked(new Date().toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" }))

    if (!result.ok) {
      setProviders([])
      setBackendState({ kind: "error", label: `Backend HTTP ${result.status || "offline"}`, detail: buildFailureMessage(result, "проверка backend") })
      return
    }

    const list = Array.isArray(result.data) ? result.data : result.data?.providers || []
    setProviders(list)
    setBackendState({
      kind: "online",
      label: "Backend отвечает",
      detail: list.length ? `Доступно провайдеров: ${list.map((item) => item.name || item.id || item).join(", ")}` : "Ответ получен, список провайдеров пуст",
    })
  }

  const runSearch = async (query) => {
    setSearchResults([])
    const result = await safeJsonFetch("/rag/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, limit: 5 }),
    })

    if (!result.ok) {
      setBackendState({ kind: "error", label: `Поиск HTTP ${result.status || "offline"}`, detail: buildFailureMessage(result, "поиск") })
      appendAssistant(buildFailureMessage(result, "поиск"), "error", "Поиск остановлен")
      return false
    }

    const results = result.data?.results || []
    setSearchResults(results)
    if (!results.length) {
      appendAssistant("Поиск выполнился, но backend вернул пустой список. Я не буду показывать выдуманные источники.", "surprised", "Поиск")
      return true
    }

    appendAssistant(
      `Нашла ${results.length} результатов в базе знаний.\n\n${results
        .map((item, index) => `${index + 1}. ${item.title || item.filename || "Результат"}${item.score ? ` - ${Math.round(item.score * 100)}%` : ""}`)
        .join("\n")}`,
      "success",
      "Поиск"
    )
    return true
  }

  const sendMessage = async () => {
    const text = input.trim()
    if (!text || loading) return

    const userMessage = { role: "user", content: text, createdAt: Date.now() }
    const nextMessages = [...messages, userMessage]
    setMessages(nextMessages)
    setInput("")
    setLoading(true)

    if (mode === "search") {
      await runSearch(text)
      setLoading(false)
      return
    }

    const result = await safeJsonFetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        messages: nextMessages.map((message) => ({ role: message.role, content: message.content })),
        mode,
        direction: workspace.primary.id,
      }),
    })

    if (!result.ok) {
      setBackendState({ kind: "error", label: `Чат HTTP ${result.status || "offline"}`, detail: buildFailureMessage(result, "чат") })
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          content: buildFailureMessage(result, "чат"),
          state: result.status === 401 || result.status === 403 ? "error" : "surprised",
          meta: `${workspace.primary.title} · ${MODES.find((item) => item.id === mode)?.label}`,
          createdAt: Date.now(),
        },
      ])
      setLoading(false)
      return
    }

    const answer = result.data?.response || result.data?.answer || result.data?.message || ""
    const provider = result.data?.provider || result.data?.model || ""
    setBackendState((current) => (current.kind === "online" ? current : { kind: "online", label: "Backend отвечает", detail: "Чат вернул результат" }))
    setMessages((current) => [
      ...current,
      {
        role: "assistant",
        content: answer || "Backend вернул пустой ответ. Я показываю это как сбой контракта, а не как успешный результат.",
        state: answer ? "happy" : "surprised",
        meta: [workspace.primary.title, provider].filter(Boolean).join(" · "),
        createdAt: Date.now(),
      },
    ])
    setLoading(false)
  }

  const onKeyDown = (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault()
      sendMessage()
    }
  }

  const useDirection = (direction) => {
    setInput(direction.prompt)
    setDrawerOpen(false)
    requestAnimationFrame(() => inputRef.current?.focus())
  }

  const resetChat = () => {
    setMessages(STARTER_MESSAGES.map((message) => ({ ...message, createdAt: Date.now() })))
    setInput("")
    setSearchResults([])
  }

  return (
    <ErrorBoundary>
      <main className="app-shell">
        <section className="assistant-panel">
          <header className="top-bar">
            <button className="icon-button mobile-only" onClick={() => setDrawerOpen(true)} aria-label="Открыть направления">
              <Icon name="menu" />
            </button>
            <div className="brand-lockup">
              <KolibriBird size={42} state={birdState} />
              <div>
                <strong>Kolibri AI</strong>
                <span>живая рабочая среда</span>
              </div>
            </div>
            <StatusPill backendState={backendState} />
          </header>

          <div className="chat-stream">
            <section className="living-identity" aria-label="Kolibri AI">
              <motion.div className="bird-stage" animate={{ y: [0, -5, 0] }} transition={{ duration: 3.2, repeat: Infinity, ease: "easeInOut" }}>
                <KolibriBird size={104} state={birdState} />
              </motion.div>
              <div className="identity-copy">
                <p className="eyebrow">Kolibri слушает задачу</p>
                <h1>Начните с чата. Инструменты появятся по смыслу.</h1>
                <p>
                  Сейчас предполагаю направление: <strong>{workspace.primary.title}</strong>. Уверенность {workspace.confidence}%.
                </p>
              </div>
            </section>

            <div className="direction-strip" aria-label="Рекомендуемые направления">
              {workspace.visible.map((direction) => (
                <button key={direction.id} className={`direction-chip ${direction.id === workspace.primary.id ? "active" : ""}`} onClick={() => useDirection(direction)}>
                  <span>{direction.label}</span>
                  {direction.title}
                </button>
              ))}
            </div>

            <section className="messages" aria-label="Диалог">
              <AnimatePresence initial={false}>
                {messages.map((message, index) => (
                  <Message key={`${message.createdAt}-${index}`} message={message} />
                ))}
                {loading ? (
                  <motion.article className="message assistant loading-message" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                    <div className="message-bird">
                      <KolibriBird size={34} state="thinking" />
                    </div>
                    <div className="message-body">
                      <div className="typing-dots"><span /><span /><span /></div>
                    </div>
                  </motion.article>
                ) : null}
              </AnimatePresence>
              <div ref={messagesEnd} />
            </section>
          </div>

          <footer className="composer-area">
            <div className="mode-row" aria-label="Режим ответа">
              {MODES.map((item) => (
                <button key={item.id} className={`mode-pill ${mode === item.id ? "active" : ""}`} onClick={() => setMode(item.id)} title={item.hint}>
                  {item.label}
                </button>
              ))}
            </div>
            <div className="input-area">
              <div className="input-wrapper">
                <textarea
                  ref={inputRef}
                  value={input}
                  onChange={(event) => setInput(event.target.value)}
                  onKeyDown={onKeyDown}
                  onInput={(event) => {
                    event.currentTarget.style.height = "auto"
                    event.currentTarget.style.height = `${Math.min(event.currentTarget.scrollHeight, 128)}px`
                  }}
                  rows={1}
                  placeholder="Опишите задачу для Kolibri..."
                  disabled={loading}
                />
                <button className="send-btn" onClick={sendMessage} disabled={loading || !input.trim()} aria-label="Отправить">
                  <Icon name={mode === "search" ? "search" : "send"} />
                </button>
              </div>
            </div>
          </footer>
        </section>

        <AnimatePresence>
          {(drawerOpen || window.innerWidth > 860) ? (
            <motion.aside
              className={`workspace-panel ${drawerOpen ? "open" : ""}`}
              initial={{ x: 32, opacity: 0 }}
              animate={{ x: 0, opacity: 1 }}
              exit={{ x: 32, opacity: 0 }}
              transition={{ duration: 0.2 }}
            >
              <div className="workspace-head">
                <div>
                  <p className="eyebrow">Рабочее поле</p>
                  <h2>{workspace.status}</h2>
                </div>
                <button className="icon-button mobile-only" onClick={() => setDrawerOpen(false)} aria-label="Закрыть">
                  <Icon name="plus" />
                </button>
              </div>

              <section className="backend-card">
                <div className="backend-title">
                  <Icon name={backendState.kind === "error" ? "warning" : "shield"} />
                  <span>{backendState.label}</span>
                </div>
                <p>{backendState.detail}</p>
                {lastChecked ? <small>Последняя проверка: {lastChecked}</small> : <small>Автозапросы отключены, чтобы не скрывать 401.</small>}
                <button className="secondary-action" onClick={checkBackend} disabled={backendState.kind === "checking"}>
                  <Icon name="refresh" />
                  {backendState.kind === "checking" ? "Проверяю..." : "Проверить backend"}
                </button>
              </section>

              <section className="tool-list" aria-label="Инструменты">
                {workspace.visible.map((direction) => (
                  <button key={direction.id} className={`tool-card ${direction.id === workspace.primary.id ? "active" : ""}`} onClick={() => useDirection(direction)}>
                    <div className="tool-icon">
                      <Icon name={direction.id === "construction" ? "layers" : direction.id === "documents" ? "file" : direction.id === "engineering" ? "bolt" : "spark"} />
                    </div>
                    <div>
                      <span>{direction.label}</span>
                      <strong>{direction.title}</strong>
                      <p>{direction.description}</p>
                    </div>
                  </button>
                ))}
              </section>

              {providers.length ? (
                <section className="compact-list">
                  <h3>Доступные провайдеры</h3>
                  {providers.map((provider) => (
                    <div key={provider.name || provider.id || provider} className="compact-row">
                      <span>{provider.name || provider.id || provider}</span>
                      <b>{provider.available === false ? "offline" : "ready"}</b>
                    </div>
                  ))}
                </section>
              ) : null}

              {searchResults.length ? (
                <section className="compact-list">
                  <h3>Результаты поиска</h3>
                  {searchResults.map((item, index) => (
                    <div key={`${item.title || item.filename || "result"}-${index}`} className="compact-row stacked">
                      <span>{item.title || item.filename || `Результат ${index + 1}`}</span>
                      <p>{item.content || item.snippet || "Без фрагмента"}</p>
                    </div>
                  ))}
                </section>
              ) : null}

              <button className="ghost-action" onClick={resetChat}>
                <Icon name="plus" />
                Новый разговор
              </button>
            </motion.aside>
          ) : null}
        </AnimatePresence>
      </main>
    </ErrorBoundary>
  )
}
