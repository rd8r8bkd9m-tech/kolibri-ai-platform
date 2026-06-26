import { useState, useRef } from 'react'
/* No framer-motion — using CSS animations */
import { useNavigate } from 'react-router'
import { Paperclip, ArrowUp, Mic, Plus } from 'lucide-react'

const quickActions = [
  'Создать смету на электромонтаж',
  'Написать договор подряда',
  'Сгенерировать отчёт',
  'Проанализировать данные',
]

export default function Home() {
  const [input, setInput] = useState('')
  const [focused, setFocused] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const navigate = useNavigate()

  const handleSend = () => {
    if (!input.trim()) return
    navigate('/chat')
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="flex flex-col items-center justify-center min-h-[100dvh] px-4 relative">
      {/* Bird */}
      <div className="mb-6 animate-scaleIn">
        <img
          src="/kolibri-bird.png"
          alt="Колибри"
          className="w-20 h-20 sm:w-24 sm:h-24 object-contain drop-shadow-lg"
        />
      </div>

      {/* Title */}
      <h1 className="text-[28px] sm:text-[32px] font-semibold text-[var(--text-primary)] tracking-tight mb-8 animate-slideUp animation-delay-100">
        Чем могу помочь?
      </h1>

      {/* Input */}
      <div className="w-full max-w-[680px] animate-slideUp animation-delay-200">
        <div
          className={`relative bg-[var(--bg-surface)] rounded-[var(--radius-xl)] border transition-all duration-200 ${
            focused
              ? 'border-[var(--accent-teal)] shadow-[0_0_0_3px_rgba(58,186,180,0.1)]'
              : 'border-[var(--border-subtle)] shadow-[var(--shadow-md)]'
          }`}
        >
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onFocus={() => setFocused(true)}
            onBlur={() => setFocused(false)}
            onKeyDown={handleKeyDown}
            placeholder="Спросите Колибри..."
            rows={1}
            className="w-full px-4 pt-3.5 pb-12 bg-transparent text-[15px] text-[var(--text-primary)] placeholder:text-[var(--text-tertiary)] resize-none outline-none leading-relaxed"
            style={{ minHeight: 56, maxHeight: 160 }}
          />

          {/* Input bottom bar */}
          <div className="absolute bottom-2 left-2 right-2 flex items-center justify-between">
            <div className="flex items-center gap-1">
              <button className="w-8 h-8 flex items-center justify-center rounded-[var(--radius-md)] text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] transition-colors">
                <Plus size={18} strokeWidth={1.8} />
              </button>
              <button className="w-8 h-8 flex items-center justify-center rounded-[var(--radius-md)] text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] transition-colors">
                <Paperclip size={18} strokeWidth={1.8} />
              </button>
              <button className="w-8 h-8 flex items-center justify-center rounded-[var(--radius-md)] text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] transition-colors">
                <Mic size={18} strokeWidth={1.8} />
              </button>
            </div>

            <button
              onClick={handleSend}
              disabled={!input.trim()}
              className={`w-8 h-8 flex items-center justify-center rounded-full transition-all duration-200 ${
                input.trim()
                  ? 'bg-[var(--accent-teal)] text-white shadow-md hover:bg-[var(--accent-teal-hover)]'
                  : 'bg-[var(--bg-elevated)] text-[var(--text-tertiary)]'
              }`}
            >
              <ArrowUp size={16} strokeWidth={2.5} />
            </button>
          </div>
        </div>

        {/* Quick Actions */}
        <div className="flex flex-wrap justify-center gap-2 mt-4">
          {quickActions.map((action, i) => (
            <button
              key={action}
              onClick={() => { setInput(action); textareaRef.current?.focus() }}
              className="px-3 py-1.5 rounded-[var(--radius-pill)] border border-[var(--border-subtle)] text-[13px] text-[var(--text-secondary)] hover:border-[var(--border-hover)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-hover)] transition-colors"
            >
              {action}
            </button>
          ))}
        </div>
      </div>

      {/* Bottom text */}
      <p className="absolute bottom-4 text-[11px] text-[var(--text-tertiary)] animate-slideUp animation-delay-400">
        AI генерирует содержимое. Проверяйте важную информацию.
      </p>
    </div>
  )
}
