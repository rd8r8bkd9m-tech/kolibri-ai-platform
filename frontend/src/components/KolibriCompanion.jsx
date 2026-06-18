import { useState, useEffect, useRef } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { KolibriBird } from "./KolibriBird"

export function KolibriCompanion({ loading, connected, messagesRef }) {
  const [state, setState] = useState("greeting")
  const [visible, setVisible] = useState(false)
  const [tooltip, setTooltip] = useState("")
  const timerRef = useRef(null)

  useEffect(() => {
    const t = setTimeout(() => setVisible(true), 2000)
    return () => clearTimeout(t)
  }, [])

  useEffect(() => {
    if (loading) {
      setState("thinking")
    } else if (!connected) {
      setState("error")
    } else {
      setState("idle")
    }
  }, [loading, connected])

  useEffect(() => {
    const el = messagesRef?.current
    if (!el) return
    let lastScroll = 0
    const onScroll = () => {
      const dir = el.scrollTop > lastScroll ? "down" : "up"
      lastScroll = el.scrollTop
      if (dir === "down" && el.scrollTop > 200) {
        setVisible(false)
      } else {
        setVisible(true)
      }
    }
    el.addEventListener("scroll", onScroll, { passive: true })
    return () => el.removeEventListener("scroll", onScroll)
  }, [messagesRef])

  const handleClick = () => {
    const tips = [
      "Попросите меня составить смету!",
      "Я могу найти документы в базе знаний.",
      "Попробуйте спросить что-нибудь.",
      "Свайпните вправо для меню.",
    ]
    const tip = tips[Math.floor(Math.random() * tips.length)]
    setTooltip(tip)
    clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => setTooltip(""), 3000)
  }

  if (!visible) return null

  return (
    <AnimatePresence>
      <motion.div
        className="kolibri-companion"
        initial={{ opacity: 0, y: 20, scale: 0.8 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 20, scale: 0.8 }}
        transition={{ duration: 0.4, type: "spring" }}
        onClick={handleClick}
      >
        <KolibriBird size={36} state={state} />
        {tooltip && (
          <motion.div
            className="kolibri-companion-tooltip"
            initial={{ opacity: 0, y: 5 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
          >
            {tooltip}
          </motion.div>
        )}
      </motion.div>
    </AnimatePresence>
  )
}
