import { useState, useEffect } from "react"
import { motion } from "framer-motion"
import { MarkdownRenderer } from "./MarkdownRenderer"

export function ThinkingBlock({ text, isStreaming }) {
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
      {expanded && <div className="thinking-content"><MarkdownRenderer>{text}</MarkdownRenderer></div>}
    </motion.div>
  )
}
