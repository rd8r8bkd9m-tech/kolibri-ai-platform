import { useState, useRef, useEffect, useCallback } from 'react'
import { useNavigate, useSearchParams } from 'react-router'
import { Paperclip, ArrowUp, Mic, User, ChevronDown, ChevronUp, Plus } from 'lucide-react'
import { chat, estimates, documents, type ChatAction } from '@/lib/api'
import StatusBird, { type BirdState } from '@/components/StatusBird'
import CartoonMascot from '@/components/CartoonMascot'

function ReasoningBlock({ text }: { text: string }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="mb-2">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 text-[12px] text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] transition-colors"
      >
        {open ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
        <span>Рассуждение{open ? '' : ` (${text.length} символов)`}</span>
      </button>
      {open && (
        <div className="mt-1.5 p-3 rounded-[var(--radius-md)] bg-[var(--bg-elevated)] border border-[var(--border-subtle)]">
          <p className="text-[12px] text-[var(--text-secondary)] leading-relaxed whitespace-pre-wrap">{text}</p>
        </div>
      )}
    </div>
  )
}

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  reasoning?: string
  actions?: ChatAction[]
  timestamp: Date
}

const WELCOME_SUGGESTIONS = [
  'Создать смету на электромонтаж дома 120 м²',
  'Написать договор подряда',
  'Проанализировать продажи за квартал',
  'Сгенерировать техническое задание',
]

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [focused, setFocused] = useState(false)
  const [loading, setLoading] = useState(false)
  const [birdState, setBirdState] = useState<BirdState>('idle')
  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()

  const handleNewChat = () => {
    setMessages([])
    setInput('')
    setBirdState('idle')
  }

  // Auto-resize textarea
  useEffect(() => {
    const ta = textareaRef.current
    if (!ta) return
    ta.style.height = 'auto'
    const lineHeight = 24
    const maxLines = 4
    const maxHeight = lineHeight * maxLines
    ta.style.height = Math.min(ta.scrollHeight, maxHeight) + 'px'
  }, [input])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Auto-send message from Home page
  useEffect(() => {
    const q = searchParams.get('q')
    if (q && messages.length === 0) {
      handleSendMessage(q)
    }
  }, [searchParams])

  const handleSendMessage = useCallback(async (text: string) => {
    if (!text.trim() || loading) return
    const userMsg: Message = { id: crypto.randomUUID(), role: 'user', content: text, timestamp: new Date() }
    setMessages(prev => [...prev, userMsg])
    setInput('')
    setLoading(true)
    setBirdState('thinking')

    try {
      const allMessages = [...messages, userMsg].map(m => ({ role: m.role, content: m.content }))
      const res = await chat.send(allMessages)
      const assistantMsg: Message = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: res.content,
        reasoning: res.reasoning || undefined,
        actions: res.actions,
        timestamp: new Date(),
      }
      setMessages(prev => [...prev, assistantMsg])
      setBirdState(res.actions?.length ? 'success' : 'ready')
      setTimeout(() => setBirdState('idle'), 2000)
    } catch {
      const errMsg: Message = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: 'Произошла ошибка при обращении к серверу. Попробуйте ещё раз.',
        timestamp: new Date(),
      }
      setMessages(prev => [...prev, errMsg])
      setBirdState('error')
      setTimeout(() => setBirdState('idle'), 2000)
    } finally {
      setLoading(false)
    }
  }, [messages, loading])

  const handleAction = async (action: ChatAction) => {
    try {
      if (action.type === 'create_estimate' && action.data) {
        const created = await estimates.create(action.data as unknown as Parameters<typeof estimates.create>[0])
        navigate(`/estimates?edit=${created.id}`)
      } else if (action.type === 'create_document' && action.data) {
        const created = await documents.create(action.data as unknown as Parameters<typeof documents.create>[0])
        navigate(`/documents?edit=${created.id}`)
      }
    } catch (e) {
      console.error('Action failed', e)
    }
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full px-4">
            <CartoonMascot state="idle" size={48} className="mb-4 opacity-75" />
            <p className="text-[15px] text-[var(--text-secondary)] mb-6">Начните новый разговор</p>
            <div className="flex flex-wrap justify-center gap-2 max-w-[500px]">
              {WELCOME_SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => handleSendMessage(s)}
                  className="px-3 py-2 rounded-[var(--radius-lg)] border border-[var(--border-subtle)] text-[13px] text-[var(--text-secondary)] hover:border-[var(--border-hover)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-hover)] transition-colors text-left"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="max-w-[720px] mx-auto py-4 space-y-1">
            <div className="sticky top-0 z-10 flex justify-end px-4 pb-2">
              <button
                onClick={handleNewChat}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-[var(--radius-md)] text-[13px] text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] border border-[var(--border-subtle)] hover:border-[var(--border-hover)] transition-colors"
              >
                <Plus size={14} strokeWidth={2} />
                Новый чат
              </button>
            </div>
            {messages.map((msg) => (
              <div
                key={msg.id}
                className={`flex gap-3 px-4 py-3 ${msg.role === 'assistant' ? 'bg-[var(--bg-secondary)]' : ''}`}
              >
                <div className="flex-shrink-0 w-7 h-7 mt-0.5">
                  {msg.role === 'user' ? (
                    <div className="w-7 h-7 rounded-full bg-[var(--bg-elevated)] flex items-center justify-center">
                      <User size={14} strokeWidth={2} className="text-[var(--text-secondary)]" />
                    </div>
                  ) : (
                    <CartoonMascot state="ready" size={28} />
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  {msg.reasoning && <ReasoningBlock text={msg.reasoning} />}
                  <p className="text-[14px] text-[var(--text-primary)] leading-relaxed whitespace-pre-wrap">{msg.content}</p>
                  {msg.actions && msg.actions.length > 0 && (
                    <div className="flex flex-wrap gap-2 mt-3">
                      {msg.actions.map((action, i) => (
                        <button
                          key={i}
                          onClick={() => handleAction(action)}
                          className="h-8 px-3 rounded-[var(--radius-md)] bg-[var(--accent-teal)] text-white text-[13px] font-medium hover:bg-[var(--accent-teal-hover)] transition-colors"
                        >
                          {action.label}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}
            {loading && (
              <div className="flex gap-3 px-4 py-3 bg-[var(--bg-secondary)]">
                <StatusBird state={birdState} size="sm" />
                <p className="text-[14px] text-[var(--text-tertiary)]">Думаю...</p>
              </div>
            )}
            <div ref={bottomRef} />
          </div>
        )}
      </div>

      <div className="border-t border-[var(--border-subtle)] bg-[var(--bg-primary)] p-3">
        <div className="max-w-[720px] mx-auto">
          <div
            className={`relative bg-[var(--bg-surface)] rounded-[var(--radius-xl)] border transition-all duration-200 ${
              focused ? 'border-[var(--accent-teal)] shadow-[0_0_0_3px_rgba(58,186,180,0.1)]' : 'border-[var(--border-subtle)] shadow-[var(--shadow-sm)]'
            }`}
          >
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onFocus={() => setFocused(true)}
              onBlur={() => setFocused(false)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSendMessage(input) } }}
              placeholder="Спросите Колибри..."
              rows={1}
              className="w-full px-4 pt-3.5 pb-12 bg-transparent text-[15px] text-[var(--text-primary)] placeholder:text-[var(--text-tertiary)] resize-none outline-none leading-relaxed"
              style={{ minHeight: 56 }}
            />
            <div className="absolute bottom-2 left-2 right-2 flex items-center justify-between">
              <div className="flex items-center gap-1">
                <button title="Скоро" className="w-8 h-8 flex items-center justify-center rounded-[var(--radius-md)] text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] transition-colors opacity-50 cursor-not-allowed">
                  <Paperclip size={18} strokeWidth={1.8} />
                </button>
                <button title="Скоро" className="w-8 h-8 flex items-center justify-center rounded-[var(--radius-md)] text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] transition-colors opacity-50 cursor-not-allowed">
                  <Mic size={18} strokeWidth={1.8} />
                </button>
              </div>
              <button
                onClick={() => handleSendMessage(input)}
                disabled={!input.trim() || loading}
                className={`w-8 h-8 flex items-center justify-center rounded-full transition-all ${
                  input.trim() && !loading ? 'bg-[var(--accent-teal)] text-white hover:bg-[var(--accent-teal-hover)]' : 'bg-[var(--bg-elevated)] text-[var(--text-tertiary)]'
                }`}
              >
                <ArrowUp size={16} strokeWidth={2.5} />
              </button>
            </div>
          </div>
          <p className="text-center text-[11px] text-[var(--text-tertiary)] mt-2">AI может ошибаться. Проверяйте важную информацию.</p>
        </div>
      </div>
    </div>
  )
}
