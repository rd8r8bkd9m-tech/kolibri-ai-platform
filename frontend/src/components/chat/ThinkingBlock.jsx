import { useEffect, useState } from "react"
import { motion } from "framer-motion"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"

export function ThinkingBlock({ text, isStreaming }) {
  const [expanded, setExpanded] = useState(isStreaming)

  useEffect(() => { if (isStreaming) setExpanded(true) }, [isStreaming])
  useEffect(() => {
    if (!isStreaming && text) {
      const timer = setTimeout(() => setExpanded(false), 2000)
      return () => clearTimeout(timer)
    }
    return undefined
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
      {expanded && (
        <div className="thinking-content">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
        </div>
      )}
    </motion.div>
  )
}
