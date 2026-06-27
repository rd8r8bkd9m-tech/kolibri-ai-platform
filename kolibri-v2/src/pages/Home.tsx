import { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router'
import { Paperclip, ArrowUp, Mic, Plus, Calculator, FileText, Bot } from 'lucide-react'
import StatusBird from '@/components/StatusBird'
import { estimates, documents, agents, type Estimate } from '@/lib/api'
import { formatDate, formatCurrency } from '@/lib/utils'

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
  const [recentEstimates, setRecentEstimates] = useState<Estimate[]>([])
  const [stats, setStats] = useState({ estimates: 0, documents: 0, agents: 0 })

  useEffect(() => {
    estimates.list({ page_size: 5 }).then(d => setRecentEstimates(d.items)).catch(() => {})
    Promise.all([
      estimates.list({ page_size: 1 }),
      documents.list({ page_size: 1 }),
      agents.list({ page_size: 100 }),
    ]).then(([e, d, a]) => {
      setStats({ estimates: e.total, documents: d.total, agents: a.items.length })
    }).catch(() => {})
  }, [])

  const handleSend = () => {
    if (!input.trim()) return
    navigate(`/chat?q=${encodeURIComponent(input.trim())}`)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="flex flex-col items-center min-h-[100dvh] px-4 pt-[15vh] relative">
      {/* Bird with wake-up animation */}
      <div className="mb-6 opacity-0 animate-wakeUp">
        <StatusBird state={focused ? 'ready' : 'idle'} size="lg" />
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
              <button title="Скоро" className="w-8 h-8 flex items-center justify-center rounded-[var(--radius-md)] text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] transition-colors opacity-50 cursor-not-allowed">
                <Plus size={18} strokeWidth={1.8} />
              </button>
              <button title="Скоро" className="w-8 h-8 flex items-center justify-center rounded-[var(--radius-md)] text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] transition-colors opacity-50 cursor-not-allowed">
                <Paperclip size={18} strokeWidth={1.8} />
              </button>
              <button title="Скоро" className="w-8 h-8 flex items-center justify-center rounded-[var(--radius-md)] text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] transition-colors opacity-50 cursor-not-allowed">
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
          {quickActions.map((action) => (
            <button
              key={action}
              onClick={() => navigate(`/chat?q=${encodeURIComponent(action)}`)}
              className="px-3 py-1.5 rounded-[var(--radius-pill)] border border-[var(--border-subtle)] text-[13px] text-[var(--text-secondary)] hover:border-[var(--border-hover)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-hover)] transition-colors"
            >
              {action}
            </button>
          ))}
        </div>
      </div>

      {/* Stats + Recent */}
      {(stats.estimates > 0 || recentEstimates.length > 0) && (
        <div className="w-full max-w-[680px] mt-10 animate-slideUp animation-delay-300">
          {/* Stats */}
          <div className="grid grid-cols-3 gap-3 mb-6">
            {[
              { icon: Calculator, label: 'Смет', value: stats.estimates, color: 'var(--accent-teal)' },
              { icon: FileText, label: 'Документов', value: stats.documents, color: 'var(--accent-lavender)' },
              { icon: Bot, label: 'Агентов', value: stats.agents, color: 'var(--accent-amber)' },
            ].map(s => (
              <button key={s.label} onClick={() => navigate(s.label === 'Смет' ? '/estimates' : s.label === 'Документов' ? '/documents' : '/agents')} className="flex items-center gap-3 p-3 rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] hover:border-[var(--border-hover)] hover:shadow-[var(--shadow-sm)] transition-all">
                <div className="w-9 h-9 rounded-[var(--radius-md)] flex items-center justify-center" style={{ background: `${s.color}15`, color: s.color }}>
                  <s.icon size={18} strokeWidth={1.8} />
                </div>
                <div className="text-left">
                  <p className="text-[18px] font-semibold text-[var(--text-primary)]">{s.value}</p>
                  <p className="text-[11px] text-[var(--text-tertiary)]">{s.label}</p>
                </div>
              </button>
            ))}
          </div>

          {/* Recent estimates */}
          {recentEstimates.length > 0 && (
            <div>
              <p className="text-[11px] font-medium text-[var(--text-tertiary)] uppercase tracking-wider mb-2">Недавние сметы</p>
              <div className="space-y-1.5">
                {recentEstimates.map(est => (
                  <button
                    key={est.id}
                    onClick={() => navigate(`/estimates?edit=${est.id}`)}
                    className="w-full flex items-center justify-between p-3 rounded-[var(--radius-md)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] hover:border-[var(--border-hover)] hover:bg-[var(--bg-hover)] transition-all text-left"
                  >
                    <div className="flex-1 min-w-0">
                      <p className="text-[13px] font-medium text-[var(--text-primary)] truncate">{est.title}</p>
                      <p className="text-[11px] text-[var(--text-tertiary)]">{est.client || '—'} · {formatDate(est.created_at)}</p>
                    </div>
                    <span className="text-[14px] font-semibold text-[var(--text-primary)] ml-3">{formatCurrency(est.total)}</span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Bottom text */}
      <p className="absolute bottom-4 text-[11px] text-[var(--text-tertiary)] animate-slideUp animation-delay-400">
        AI генерирует содержимое. Проверяйте важную информацию.
      </p>
    </div>
  )
}
