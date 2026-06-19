import { useState, useEffect, useRef, useCallback } from "react"
import { motion, AnimatePresence } from "framer-motion"
import mascotImg from "../assets/kolibri-mascot.png"

const STATE_LABELS = {
  idle: "спокойна", greeting: "приветствует", listening: "слушает",
  thinking: "думает", writing: "пишет", learning: "учится",
  success: "готово", error: "нужна помощь", happy: "радуется",
  surprised: "удивлена", "angry-soft": "сердится мягко",
  calm: "спокойна", sleepy: "спит", flying: "летит",
  petted: "довольна", waving: " машет", excited: "в восторге",
}

const TIPS = [
  "Попросите меня составить смету!",
  "Я могу найти документы в базе знаний.",
  "Попробуйте спросить что-нибудь.",
  "Свайпните вправо для меню.",
  "Я учусь на каждом вашем вопросе!",
  "Попробуйте: 'Составь смету на ремонт'",
  "Я могу искать в интернете!",
  "Двойной клик — и я расскажу секрет!",
]

const SECRETS = [
  "Я Колибри — самая быстрая птичка в AI!",
  "Мой движок FormuLaLM — уникальное изобретение.",
  "Я работаю на 6 серверах одновременно!",
  "Моя память хранит все наши разговоры.",
  "Я могу генерировать PDF-документы!",
]

export function KolibriBird({ state = "idle", size = 56, className = "" }) {
  const px = typeof size === "number" ? size : 56

  const bodyAnimate =
    state === "thinking" || state === "learning"
      ? { y: [0, -3, 0], rotate: [-2, 2, -2] }
      : state === "flying" || state === "excited"
        ? { x: [0, 4, 0], y: [0, -5, 0], rotate: [-4, 4, -4] }
        : state === "success" || state === "happy"
          ? { scale: [1, 1.1, 1], y: [0, -3, 0] }
          : state === "error"
            ? { rotate: [0, -4, 4, 0] }
            : state === "petted"
              ? { scale: [1, 1.05, 0.98, 1.03, 1] }
              : state === "waving"
                ? { rotate: [0, -8, 8, -8, 0] }
                : state === "sleepy"
                  ? { y: [0, 1, 0], rotate: [0, -2, 0] }
                  : { y: [0, -2, 0] }

  const dur = state === "error" ? 0.3 : state === "petted" ? 0.6 : state === "sleepy" ? 3 : 1.5
  const repeat = state === "idle" || state === "calm" ? Infinity : state === "petted" ? 0 : Infinity

  return (
    <motion.div
      className={`kolibri-mascot kolibri-mascot--${state} ${className}`}
      style={{
        width: px, height: px, borderRadius: "50%", overflow: "hidden",
        flexShrink: 0, display: "inline-flex", alignItems: "center", justifyContent: "center",
        position: "relative", cursor: "pointer",
      }}
      animate={bodyAnimate}
      transition={{ duration: dur, repeat, ease: "easeInOut" }}
      aria-label={`Колибри ${STATE_LABELS[state] || state}`}
      role="img"
    >
      <img
        src={mascotImg} alt="Колибри" draggable={false}
        style={{
          width: "100%", height: "100%", objectFit: "cover",
          display: "block", userSelect: "none",
          filter: state === "sleepy" ? "brightness(0.7) saturate(0.5)"
            : state === "error" ? "hue-rotate(340deg)"
            : state === "happy" || state === "excited" ? "saturate(1.3) brightness(1.1)"
            : "none",
        }}
      />
      {state === "thinking" && (
        <motion.div style={{
          position: "absolute", top: -2, right: -2, display: "flex", gap: 2,
        }}>
          {[0, 1, 2].map(i => (
            <motion.div key={i}
              style={{ width: 4, height: 4, borderRadius: "50%", background: "#3b82f6" }}
              animate={{ opacity: [0.3, 1, 0.3], y: [0, -4, 0] }}
              transition={{ duration: 0.8, repeat: Infinity, delay: i * 0.2 }}
            />
          ))}
        </motion.div>
      )}
      {state === "success" && (
        <motion.div
          style={{ position: "absolute", top: -4, fontSize: 12 }}
          initial={{ opacity: 0, y: 0, scale: 0.5 }}
          animate={{ opacity: [0, 1, 0], y: -12, scale: 1 }}
          transition={{ duration: 0.8 }}
        >
          ✨
        </motion.div>
      )}
    </motion.div>
  )
}

export function KolibriCompanion({ loading, connected, messagesRef }) {
  const [state, setState] = useState("greeting")
  const [visible, setVisible] = useState(false)
  const [tooltip, setTooltip] = useState("")
  const [sparkles, setSparkles] = useState([])
  const timerRef = useRef(null)
  const clickCountRef = useRef(0)
  const lastActivityRef = useRef(Date.now())

  useEffect(() => {
    const t = setTimeout(() => setVisible(true), 1500)
    return () => clearTimeout(t)
  }, [])

  useEffect(() => {
    if (loading) setState("thinking")
    else if (!connected) setState("error")
    else setState("idle")
  }, [loading, connected])

  // Sleep after inactivity
  useEffect(() => {
    const interval = setInterval(() => {
      const idle = Date.now() - lastActivityRef.current
      if (idle > 120_000 && state === "idle") setState("sleepy")
    }, 30_000)
    return () => clearInterval(interval)
  }, [state])

  // Wake on activity
  const wakeUp = useCallback(() => {
    lastActivityRef.current = Date.now()
    if (state === "sleepy") {
      setState("surprised")
      setTimeout(() => setState("idle"), 1500)
    }
  }, [state])

  useEffect(() => {
    const el = messagesRef?.current
    if (!el) return
    let lastScroll = 0
    const onScroll = () => {
      wakeUp()
      const dir = el.scrollTop > lastScroll ? "down" : "up"
      lastScroll = el.scrollTop
      if (dir === "down" && el.scrollTop > 200) setVisible(false)
      else setVisible(true)
    }
    el.addEventListener("scroll", onScroll, { passive: true })
    return () => el.removeEventListener("scroll", onScroll)
  }, [messagesRef, wakeUp])

  const handleClick = () => {
    wakeUp()
    clickCountRef.current += 1

    // Double click = secret
    if (clickCountRef.current >= 2) {
      const secret = SECRETS[Math.floor(Math.random() * SECRETS.length)]
      setTooltip(secret)
      setState("excited")
      setSparkles(prev => [...prev, { id: Date.now(), x: Math.random() * 40 - 20, y: -20 }])
      setTimeout(() => setState("idle"), 2000)
      clickCountRef.current = 0
    } else {
      const tip = TIPS[Math.floor(Math.random() * TIPS.length)]
      setTooltip(tip)
      setState("waving")
      setTimeout(() => setState("idle"), 1200)
      setTimeout(() => { clickCountRef.current = 0 }, 400)
    }

    clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => setTooltip(""), 4000)
  }

  const handleMouseEnter = () => {
    wakeUp()
    if (state === "idle") setState("happy")
  }
  const handleMouseLeave = () => {
    if (state === "happy") setState("idle")
  }

  if (!visible) return null

  return (
    <AnimatePresence>
      <motion.div
        className="kolibri-companion"
        initial={{ opacity: 0, y: 20, scale: 0.8 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 20, scale: 0.8 }}
        transition={{ duration: 0.5, type: "spring" }}
        onClick={handleClick}
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
        style={{ position: "relative" }}
      >
        <KolibriBird size={42} state={state} />

        {/* Sparkles on double click */}
        {sparkles.map(s => (
          <motion.div key={s.id}
            style={{
              position: "absolute", top: "50%", left: "50%",
              fontSize: 10, pointerEvents: "none",
            }}
            initial={{ opacity: 1, x: 0, y: 0 }}
            animate={{ opacity: 0, x: s.x, y: s.y }}
            transition={{ duration: 1 }}
            onAnimationComplete={() => setSparkles(prev => prev.filter(p => p.id !== s.id))}
          >
            ✨
          </motion.div>
        ))}

        {tooltip && (
          <motion.div
            className="kolibri-companion-tooltip"
            initial={{ opacity: 0, y: 5, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0 }}
          >
            {tooltip}
          </motion.div>
        )}

        {/* State indicator dot */}
        <motion.div
          style={{
            position: "absolute", bottom: 0, right: 0,
            width: 8, height: 8, borderRadius: "50%",
            background: state === "error" ? "#ef4444"
              : state === "thinking" || state === "learning" ? "#3b82f6"
              : state === "happy" || state === "excited" ? "#10b981"
              : state === "sleepy" ? "#6b7280"
              : "#10b981",
            border: "1.5px solid var(--bg-primary, #0a0a0f)",
          }}
          animate={state === "thinking" ? { scale: [1, 1.3, 1] } : {}}
          transition={{ duration: 0.8, repeat: Infinity }}
        />
      </motion.div>
    </AnimatePresence>
  )
}
