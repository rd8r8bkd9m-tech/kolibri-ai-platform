import { useEffect, useMemo, useState } from "react"
import { KolibriBird } from "./KolibriBird"

const taskStateMap = {
  queued: "working",
  running: "working",
  started: "working",
  completed: "success",
  failed: "error",
}

const birdStateMap = {
  idle: "idle",
  listening: "listening",
  thinking: "thinking",
  working: "learning",
  success: "success",
  warning: "surprised",
  error: "error",
  offline: "sleepy",
  sleepy: "sleepy",
  celebrating: "happy",
}

const transientDurations = {
  listening: 1800,
  thinking: 2200,
  working: 2400,
  success: 1800,
  warning: 2200,
  error: 2600,
  celebrating: 2400,
}

function usePrefersReducedMotion() {
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(false)

  useEffect(() => {
    const media = window.matchMedia?.("(prefers-reduced-motion: reduce)")
    if (!media) return undefined
    const update = () => setPrefersReducedMotion(media.matches)
    update()
    media.addEventListener?.("change", update)
    return () => media.removeEventListener?.("change", update)
  }, [])

  return prefersReducedMotion
}

export function LivingKolibri({
  state = "idle",
  taskState = "",
  personality = "calm",
  reducedMotion,
  size = 72,
  className = "",
}) {
  const prefersReducedMotion = usePrefersReducedMotion()
  const [eventState, setEventState] = useState(null)

  useEffect(() => {
    const handlers = {
      "chat:focus": () => setEventState("listening"),
      "chat:blur": () => setEventState(null),
      "chat:send": () => setEventState("thinking"),
      "ai:thinking": () => setEventState("thinking"),
      "factory:task_started": () => setEventState("working"),
      "factory:task_completed": () => setEventState("success"),
      "factory:task_failed": () => setEventState("error"),
      "billing:success": () => setEventState("celebrating"),
      "network:offline": () => setEventState("offline"),
      "network:online": () => setEventState("success"),
    }

    Object.entries(handlers).forEach(([eventName, handler]) => {
      window.addEventListener(eventName, handler)
    })

    return () => {
      Object.entries(handlers).forEach(([eventName, handler]) => {
        window.removeEventListener(eventName, handler)
      })
    }
  }, [])

  useEffect(() => {
    if (!eventState || eventState === "offline") return undefined
    const duration = transientDurations[eventState]
    if (!duration) return undefined
    const timer = window.setTimeout(() => setEventState(null), duration)
    return () => window.clearTimeout(timer)
  }, [eventState])

  const appState = useMemo(() => {
    return eventState || taskStateMap[taskState] || state || "idle"
  }, [eventState, state, taskState])

  const visualState = birdStateMap[appState] || "idle"
  const motionDisabled = reducedMotion ?? prefersReducedMotion

  return (
    <div
      className={`living-kolibri living-kolibri--${appState} ${className}`}
      data-state={appState}
      data-personality={personality}
      aria-live="polite"
    >
      <KolibriBird state={visualState} size={size} reducedMotion={motionDisabled} />
    </div>
  )
}
