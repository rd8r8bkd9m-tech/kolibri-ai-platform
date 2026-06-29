import { motion } from "framer-motion"

export function ChatComposer({ inputRef, value, loading, onChange, onSend, onFocus, onBlur }) {
  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      onSend()
    }
  }

  return (
    <div className="input-area">
      <div className="input-wrapper">
        <textarea ref={inputRef} value={value} onChange={e => onChange(e.target.value)} onKeyDown={handleKeyDown}
          placeholder="Напишите задачу по смете, КП или документам..." rows={1} disabled={loading}
          onFocus={onFocus}
          onBlur={onBlur}
          onInput={e => { e.target.style.height = "auto"; e.target.style.height = Math.min(e.target.scrollHeight, 120) + "px" }} />
        <motion.button onClick={onSend} disabled={loading || !value.trim()} className="send-btn"
          type="button" aria-label="Отправить сообщение"
          whileHover={{ scale: 1.08 }} whileTap={{ scale: 0.92 }}>
          {loading ? (
            <motion.svg className="spinner-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"
              animate={{ rotate: 360 }} transition={{ duration: 1, repeat: Infinity, ease: "linear" }}>
              <path d="M21 12a9 9 0 11-6.219-8.56"/>
            </motion.svg>
          ) : (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>
          )}
        </motion.button>
      </div>
    </div>
  )
}
