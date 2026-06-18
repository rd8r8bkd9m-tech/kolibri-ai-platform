import { motion } from "framer-motion"
import { KolibriBird } from "./KolibriBird"
import { EstimateFolderCard } from "./EstimateFolderCard"
import { ThinkingBlock } from "./ThinkingBlock"
import { MarkdownRenderer } from "./MarkdownRenderer"
import { WelcomeScreen } from "./WelcomeScreen"

function formatTime(ts) {
  if (!ts) return ""
  const d = new Date(ts)
  return d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })
}

function parseThinking(text) {
  const match = text.match(/<thinking>([\s\S]*?)<\/thinking>/)
  if (match) return { thinking: match[1].trim(), content: text.replace(/<thinking>[\s\S]*?<\/thinking>/, "").trim() }
  return { thinking: null, content: text }
}

function isEstimateJson(text) {
  if (!text) return false
  const trimmed = text.trim()
  return trimmed.startsWith('{') && (
    trimmed.includes('"смета"') ||
    (trimmed.includes('"title"') && trimmed.includes('"items"'))
  )
}

export function MessageList({ messages, loading, quickActions, onQuickAction, onCanvasAction, messagesRef }) {
  return (
    <div className="messages" ref={messagesRef}>
      {messages.length === 0 && (
        <WelcomeScreen quickActions={quickActions} onAction={onQuickAction} />
      )}
      {messages.map((msg, i) => {
        const { thinking, content } = msg.role === "assistant" ? parseThinking(msg.content || "") : { thinking: null, content: msg.content }
        const hasCanvas = msg.canvas && (Array.isArray(msg.canvas) ? msg.canvas.length > 0 : true)
        const isEstimate = hasCanvas && msg.canvas?.type === "estimate"
        const hideContent = isEstimate && isEstimateJson(content)

        return (
          <motion.div key={i} className={`message ${msg.role}`}
            initial={{ opacity: 0, y: 10, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ duration: 0.25, type: "spring", stiffness: 200 }}>
            <div className={`message-avatar ${msg.role}`}>
              {msg.role === "assistant" ? <KolibriBird size={20} state={msg.streaming ? "thinking" : "happy"} /> : "U"}
            </div>
            <div className="message-bubble">
              {msg.role === "assistant" && <ThinkingBlock text={thinking} isStreaming={msg.streaming} />}
              {!hideContent && !isEstimate && (
                msg.role === "assistant" ? (
                  <MarkdownRenderer>{content || (msg.streaming ? "..." : "")}</MarkdownRenderer>
                ) : <p>{msg.content}</p>
              )}
              {isEstimate && (
                <>
                  <EstimateFolderCard
                    data={msg.canvas.data}
                    onClick={() => onCanvasAction("edit", msg.canvas)}
                  />
                </>
              )}
              <div className="message-meta">
                {msg.timestamp && <span className="message-time">{formatTime(msg.timestamp)}</span>}
                {msg.provider && msg.role === "assistant" && (
                  <motion.span className="provider-badge" initial={{ opacity: 0, scale: 0.8 }} animate={{ opacity: 1, scale: 1 }}>
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg> {msg.provider}
                  </motion.span>
                )}
              </div>
            </div>
          </motion.div>
        )
      })}
      {loading && !messages.some(m => m.streaming) && (
        <motion.div className="message assistant" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
          <div className="message-avatar assistant"><KolibriBird size={20} state="thinking" /></div>
          <div className="message-bubble typing-indicator">
            <span></span><span></span><span></span>
          </div>
        </motion.div>
      )}
    </div>
  )
}
