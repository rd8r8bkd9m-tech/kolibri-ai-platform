import { useState } from "react"
import { motion } from "framer-motion"

export function CopyButton({ text }) {
  const [copied, setCopied] = useState(false)
  const handleCopy = async () => {
    try { await navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 2000) } catch { /* clipboard denied */ }
  }
  return (
    <motion.button className="code-copy-btn" onClick={handleCopy} aria-label={copied ? "Скопировано" : "Копировать код"} whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}>
      {copied ? (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><polyline points="20 6 9 17 4 12"/></svg>
      ) : (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>
      )}
    </motion.button>
  )
}

export function CodeBlock({ children, className }) {
  const code = String(children).replace(/\n$/, "")
  const lang = className?.replace("language-", "") || ""
  return (
    <div className="code-block-wrapper">
      <div className="code-block-header">
        <span className="code-block-lang">{lang || "code"}</span>
        <CopyButton text={code} />
      </div>
      <pre><code className={className}>{code}</code></pre>
    </div>
  )
}
