import { motion } from "framer-motion"
import { MessageList } from "./MessageList"
import { MessageInput } from "./MessageInput"

export function ChatView({ messages, loading, input, setInput, onSend, quickActions, onQuickAction, onCanvasAction, messagesRef, inputRef }) {
  return (
    <motion.div key="chat" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }}
      transition={{ duration: 0.2 }} style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0, overflow: "hidden" }}>
      <MessageList
        messages={messages}
        loading={loading}
        quickActions={quickActions}
        onQuickAction={onQuickAction}
        onCanvasAction={onCanvasAction}
        messagesRef={messagesRef}
      />
      <MessageInput
        input={input}
        setInput={setInput}
        loading={loading}
        onSend={onSend}
        inputRef={inputRef}
      />
    </motion.div>
  )
}
