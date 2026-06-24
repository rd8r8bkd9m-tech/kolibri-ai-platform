import { useEffect, useMemo, useRef, useState } from "react"
import {
  CircleStop,
  Plus,
  Send,
} from "lucide-react"
import { visibleActions } from "./contracts.js"
import { CanvasStage } from "./CanvasStage.jsx"
import { dispatchCanvasAction, loadBirdStatus, loadCanvasScreen, requestCanvasTurn } from "./canvasRuntime.js"
import { mixCanvasTheme, resolveCanvasTheme } from "./canvasTheme.js"
import { loadProfile } from "./personalization.js"

const CANVAS_REQUEST_TIMEOUT_MS = 240000
const BIRD_STATUS_REFRESH_MS = 10000
const MAX_VISIBLE_TURNS = 6

function App() {
  const [theme] = useState(() => localStorage.getItem("kolibri-v3-theme") || "dark")
  const [timeSignal, setTimeSignal] = useState(() => Date.now())
  const [profile] = useState(loadProfile)
  const [canvas, setCanvas] = useState(null)
  const [birdStatus, setBirdStatus] = useState(null)
  const [input, setInput] = useState("")
  const [busy, setBusy] = useState(false)
  const [actionsOpen, setActionsOpen] = useState(false)
  const [pendingApproval, setPendingApproval] = useState(null)
  const [visibleTurns, setVisibleTurns] = useState([])
  const [runtimeProgress, setRuntimeProgress] = useState(null)
  const [paintedTheme, setPaintedTheme] = useState(() => resolveCanvasTheme())
  const abortRef = useRef(null)
  const submitLockRef = useRef(false)
  const actionLockRef = useRef(false)
  const paintedThemeRef = useRef(paintedTheme)
  const themeTransitionRef = useRef(null)

  const actions = useMemo(() => visibleActions(canvas?.manifest, {
    profileId: profile.id,
    opsMode: false,
    maxActions: 4,
    state: canvas?.manifest?.state || "",
  }), [canvas, profile.id])
  const lastVisibleTurn = visibleTurns.length ? visibleTurns[visibleTurns.length - 1] : null
  const canvasTheme = useMemo(() => resolveCanvasTheme({
    now: new Date(timeSignal),
    text: `${lastVisibleTurn?.text || ""} ${canvas?.lastUserText || ""} ${input || ""}`,
    manifestTheme: canvas?.manifest?.theme || canvas?.manifest?.display?.theme || null,
  }), [canvas, input, lastVisibleTurn, timeSignal])

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    localStorage.setItem("kolibri-v3-theme", theme)
  }, [theme])

  useEffect(() => {
    document.documentElement.dataset.canvasTheme = canvasTheme.name
  }, [canvasTheme.name])

  useEffect(() => {
    paintedThemeRef.current = paintedTheme
  }, [paintedTheme])

  useEffect(() => {
    const root = document.documentElement
    root.style.setProperty("--kolibri-accent", paintedTheme.accent)
    root.style.setProperty("--kolibri-accent-soft", paintedTheme.accentSoft)
    root.style.setProperty("--kolibri-text", paintedTheme.text)
    root.style.setProperty("--kolibri-muted", paintedTheme.textMuted)
    root.style.setProperty("--kolibri-panel-fill", paintedTheme.panelFill)
    root.style.setProperty("--kolibri-panel-stroke", paintedTheme.panelStroke)
  }, [paintedTheme])

  useEffect(() => {
    const from = themeTransitionRef.current?.target || paintedThemeRef.current
    const startedAt = performance.now()
    const durationMs = 900
    let frame = 0
    themeTransitionRef.current = { target: canvasTheme }

    function animate(now) {
      const progress = Math.min(1, (now - startedAt) / durationMs)
      setPaintedTheme(mixCanvasTheme(from, canvasTheme, easeInOut(progress)))
      if (progress < 1) frame = window.requestAnimationFrame(animate)
    }

    frame = window.requestAnimationFrame(animate)
    return () => window.cancelAnimationFrame(frame)
  }, [canvasTheme])

  useEffect(() => {
    const interval = window.setInterval(() => setTimeSignal(Date.now()), 60000)
    return () => window.clearInterval(interval)
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    loadCanvasScreen("shell", controller.signal).then(result => {
      if (result.canvas !== undefined) setCanvas(result.canvas)
    })
    return () => controller.abort()
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    let disposed = false
    async function refreshBirdStatus() {
      const status = await loadBirdStatus(controller.signal)
      if (!disposed) setBirdStatus(status)
    }
    refreshBirdStatus()
    const interval = window.setInterval(refreshBirdStatus, BIRD_STATUS_REFRESH_MS)
    return () => {
      disposed = true
      window.clearInterval(interval)
      controller.abort()
    }
  }, [])

  async function submitPrompt(event) {
    event?.preventDefault()
    const text = input.trim()
    if (!text || busy || submitLockRef.current) return
    submitLockRef.current = true
    const turnId = createTurnId()
    setInput("")
    setBusy(true)
    appendVisibleTurn({ id: turnId, role: "user", text, status: "queued" })
    setRuntimeProgress(progressState("queued", "Запрос принят"))
    const { controller, clear } = createTimedController(CANVAS_REQUEST_TIMEOUT_MS)
    abortRef.current = controller
    try {
      setRuntimeProgress(progressState("sending", "Отправляю в runtime"))
      const result = await requestCanvasTurn({
        userText: text,
        profile,
        canvas,
        signal: controller.signal,
      })
      setRuntimeProgress(progressState("painting", "Обновляю холст"))
      if (result.canvas !== undefined) setCanvas(result.canvas)
      updateVisibleTurn(turnId, {
        status: result.errorName ? "error" : "done",
        assistantText: result.assistantText || "",
      })
      setRuntimeProgress(progressState(result.errorName ? "error" : "done", result.errorName ? "Нужна проверка" : "Готово"))
      refreshBirdStatusSoon()
    } finally {
      clear()
      if (abortRef.current === controller) abortRef.current = null
      submitLockRef.current = false
      setBusy(false)
      window.setTimeout(() => setRuntimeProgress(current => current?.stage === "done" ? null : current), 1400)
    }
  }

  async function runAction(action) {
    if (busy || actionLockRef.current) return
    if (needsApproval(action)) {
      setActionsOpen(false)
      setPendingApproval(action)
      setRuntimeProgress(progressState("approval", "Ожидаю подтверждение"))
      return
    }
    await executeAction(action)
  }

  async function approvePendingAction() {
    if (!pendingApproval || busy || actionLockRef.current) return
    const action = { ...pendingApproval, confirmed: true }
    setPendingApproval(null)
    await executeAction(action)
  }

  function cancelPendingAction() {
    if (busy) return
    setPendingApproval(null)
    setRuntimeProgress(null)
  }

  async function executeAction(action) {
    if (actionLockRef.current) return
    actionLockRef.current = true
    setBusy(true)
    setRuntimeProgress(progressState("action", "Выполняю действие"))
    const { controller, clear } = createTimedController(CANVAS_REQUEST_TIMEOUT_MS)
    abortRef.current = controller
    try {
      const result = await dispatchCanvasAction({
        action,
        profile,
        canvas,
        signal: controller.signal,
      })
      setRuntimeProgress(progressState("painting", "Обновляю холст"))
      if (result.canvas !== undefined) setCanvas(result.canvas)
      setRuntimeProgress(progressState(result.errorName ? "error" : "done", result.errorName ? "Нужна проверка" : "Готово"))
      refreshBirdStatusSoon()
    } finally {
      clear()
      if (abortRef.current === controller) abortRef.current = null
      actionLockRef.current = false
      setBusy(false)
      window.setTimeout(() => setRuntimeProgress(current => current?.stage === "done" ? null : current), 1400)
    }
  }

  function stop() {
    abortRef.current?.abort()
    setBusy(false)
    setRuntimeProgress(progressState("stopped", "Запрос остановлен"))
  }

  function appendVisibleTurn(turn) {
    setVisibleTurns(current => [...current, turn].slice(-MAX_VISIBLE_TURNS))
  }

  function updateVisibleTurn(id, patch) {
    setVisibleTurns(current => current.map(turn => turn.id === id ? { ...turn, ...patch } : turn).slice(-MAX_VISIBLE_TURNS))
  }

  function refreshBirdStatusSoon() {
    const controller = new AbortController()
    const timeoutId = window.setTimeout(() => controller.abort(), 2500)
    loadBirdStatus(controller.signal)
      .then(status => setBirdStatus(status))
      .catch(() => {})
      .finally(() => window.clearTimeout(timeoutId))
  }

  return (
    <main className="canvas-shell">
      <section className="screen-canvas" aria-label="Единый canvas">
        <CanvasStage
          canvas={canvas}
          birdStatus={birdStatus}
          actions={actions}
          showActions={actionsOpen && actions.length > 0}
          pendingApproval={pendingApproval}
          visibleTurns={visibleTurns}
          runtimeProgress={runtimeProgress}
          canvasTheme={paintedTheme}
          onAction={runAction}
          onApproveAction={approvePendingAction}
          onCancelApproval={cancelPendingAction}
          busy={busy}
        />

        <form className="composer" onSubmit={submitPrompt}>
          <button
            type="button"
            className="round-button"
            onClick={() => setActionsOpen(value => actions.length > 0 ? !value : false)}
            aria-label={actions.length > 0 ? "Открыть инструменты" : "Инструменты появятся по контексту"}
            disabled={actions.length === 0}
          >
            <Plus size={22} />
          </button>
          <textarea
            value={input}
            onChange={event => setInput(event.target.value)}
            placeholder=""
            aria-label="Поле ввода промпта"
            rows={1}
            onKeyDown={event => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault()
                submitPrompt(event)
              }
            }}
          />
          <button type={busy ? "button" : "submit"} onClick={busy ? stop : undefined} className="send-button" aria-label={busy ? "Остановить" : "Отправить"}>
            {busy ? <CircleStop size={20} /> : <Send size={20} />}
          </button>
        </form>
      </section>
    </main>
  )
}

function needsApproval(action) {
  if (!action) return false
  return Boolean(action.requiresConfirmation) || ["review", "paid", "destructive"].includes(action.risk)
}

function createTurnId() {
  return `turn-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function progressState(stage, label) {
  return {
    stage,
    label,
    updatedAt: Date.now(),
  }
}

function easeInOut(value) {
  return value < 0.5 ? 2 * value * value : 1 - ((-2 * value + 2) ** 2) / 2
}

function createTimedController(timeoutMs) {
  const controller = new AbortController()
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs)
  return {
    controller,
    clear: () => window.clearTimeout(timeoutId),
  }
}

export default App
