import { motion } from "framer-motion"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { KolibriBird } from "../KolibriBird"
import { ThinkingBlock } from "./ThinkingBlock"

function parseThinking(text) {
  const match = text.match(/<thinking>([\s\S]*?)<\/thinking>/)
  if (match) return { thinking: match[1].trim(), content: text.replace(/<thinking>[\s\S]*?<\/thinking>/, "").trim() }
  return { thinking: null, content: text }
}

export function MessageList({ messages, messagesEndRef }) {
  return (
    <>
      {messages.map((msg, i) => {
        const { thinking, content } = msg.role === "assistant" ? parseThinking(msg.content || "") : { thinking: null, content: msg.content }
        return (
          <motion.div key={i} className={`message ${msg.role}`}
            initial={{ opacity: 0, y: 10, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ duration: 0.25, type: "spring", stiffness: 200 }}>
            <div className={`message-avatar ${msg.role}`}>
              {msg.role === "assistant" ? <KolibriBird size={20} state={msg.streaming ? "thinking" : "happy"} /> : "U"}
            </div>
            <div className="message-bubble">
              {msg.role === "assistant" && <ThinkingBlock text={thinking} isStreaming={msg.streaming} />}
              {msg.role === "assistant" ? (
                content ? <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown> : <div className="typing-indicator"><span></span><span></span><span></span></div>
              ) : <p>{msg.content}</p>}
              {msg.provider && msg.role === "assistant" && (
                <motion.div className="provider-badge" initial={{ opacity: 0, scale: 0.8 }} animate={{ opacity: 1, scale: 1 }}>
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg> {msg.provider}
                </motion.div>
              )}
            </div>
          </motion.div>
        )
      })}
      <div ref={messagesEndRef} />
    </>
  )
}
