import { useState, useRef, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router'
import { Paperclip, ArrowUp, Mic, User, ChevronDown, ChevronUp, Plus } from 'lucide-react'
import { chat, estimates, documents, type ChatAction } from '@/lib/api'
import MascotAnimation from '@/components/MascotAnimation'
import StatusBird, { type BirdState } from '@/components/StatusBird'

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

const CHAT_TIMEOUT_MS = 20000

function readInitialPrompt() {
  const stored = sessionStorage.getItem('kolibri_initial_prompt')
  if (stored) return stored

  const hashQuery = window.location.hash.includes('?') ? window.location.hash.split('?')[1] : ''
  return new URLSearchParams(hashQuery).get('q') || new URLSearchParams(window.location.search).get('q') || ''
}

function createMessageId() {
  if (crypto.randomUUID) return crypto.randomUUID()
  return `msg-${Date.now()}-${Math.random().toString(36).slice(2)}`
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([])
  const [initialPrompt] = useState(readInitialPrompt)
  const [input, setInput] = useState('')
  const [focused, setFocused] = useState(false)
  const [loading, setLoading] = useState(false)
  const [lastFailedPrompt, setLastFailedPrompt] = useState('')
  const [birdState, setBirdState] = useState<BirdState>('idle')
  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const navigate = useNavigate()

  const handleNewChat = () => {
    setMessages([])
    setInput('')
    setLastFailedPrompt('')
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

  const handleSendMessage = useCallback(async (text: string) => {
    if (!text.trim() || loading) return
    const userMsg: Message = { id: createMessageId(), role: 'user', content: text, timestamp: new Date() }
    setMessages(prev => [...prev, userMsg])
    setInput('')
    setLastFailedPrompt('')
    setLoading(true)
    setBirdState('thinking')

    const controller = new AbortController()
    const timeout = window.setTimeout(() => controller.abort(), CHAT_TIMEOUT_MS)
    try {
      const allMessages = [...messages, userMsg].map(m => ({ role: m.role, content: m.content }))
      const res = await chat.send(allMessages, controller.signal)
      const assistantMsg: Message = {
        id: createMessageId(),
        role: 'assistant',
        content: res.content,
        reasoning: res.reasoning || undefined,
        actions: res.actions,
        timestamp: new Date(),
      }
      setMessages(prev => [...prev, assistantMsg])
      setBirdState(res.actions?.length ? 'success' : 'ready')
      setTimeout(() => setBirdState('idle'), 2000)
    } catch (error) {
      const timedOut = error instanceof DOMException && error.name === 'AbortError'
      const errMsg: Message = {
        id: createMessageId(),
        role: 'assistant',
        content: timedOut
          ? 'Ответ занимает слишком много времени. Соединение остановлено, можно повторить запрос.'
          : 'Произошла ошибка при обращении к серверу. Попробуйте ещё раз.',
        timestamp: new Date(),
      }
      setMessages(prev => [...prev, errMsg])
      setLastFailedPrompt(text)
      setBirdState('error')
      setTimeout(() => setBirdState('idle'), 2000)
    } finally {
      window.clearTimeout(timeout)
      setLoading(false)
    }
  }, [messages, loading])

  // Auto-send the prompt passed from Home or a direct #/chat?q=... link once.
  useEffect(() => {
    if (!initialPrompt || messages.length > 0) return
    sessionStorage.removeItem('kolibri_initial_prompt')
    handleSendMessage(initialPrompt)
  }, [handleSendMessage, initialPrompt, messages.length])

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
    <div className="flex h-full min-h-0 flex-col md:h-full">
      <div className="flex-1 min-h-0 overflow-y-auto overscroll-contain">
        {messages.length === 0 ? (
          <div className="flex min-h-full flex-col items-center justify-center px-4 py-6">
            <MascotAnimation state="idle" className="mb-4 h-16 w-16" decorative />
            <p className="text-[15px] text-[var(--text-secondary)] mb-6">Начните новый разговор</p>
            <div className="flex flex-wrap justify-center gap-2 max-w-[500px]">
              {WELCOME_SUGGESTIONS.map((s) => (
                <button
                  type="button"
                  key={s}
                  onClick={() => handleSendMessage(s)}
                  className="min-h-11 px-3 py-2 rounded-[var(--radius-lg)] border border-[var(--border-subtle)] text-[13px] text-[var(--text-secondary)] hover:border-[var(--border-hover)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-hover)] transition-colors text-left break-words"
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
                type="button"
                onClick={handleNewChat}
                className="flex min-h-10 items-center gap-1.5 px-3 py-1.5 rounded-[var(--radius-md)] text-[13px] text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] border border-[var(--border-subtle)] hover:border-[var(--border-hover)] transition-colors bg-[var(--bg-primary)]/90 backdrop-blur-md"
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
                    <MascotAnimation state="ready" className="h-7 w-7" decorative />
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  {msg.reasoning && <ReasoningBlock text={msg.reasoning} />}
                  <p className="text-[14px] text-[var(--text-primary)] leading-relaxed whitespace-pre-wrap break-words [overflow-wrap:anywhere]">{msg.content}</p>
                  {msg.actions && msg.actions.length > 0 && (
                    <div className="flex flex-wrap gap-2 mt-3">
                      {msg.actions.map((action, i) => (
                        <button
                          key={i}
                          type="button"
                          onClick={() => handleAction(action)}
                          className="min-h-10 px-3 rounded-[var(--radius-md)] bg-[var(--accent-teal)] text-white text-[13px] font-medium hover:bg-[var(--accent-teal-hover)] transition-colors"
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
                <div className="min-w-0">
                  <p className="text-[14px] text-[var(--text-tertiary)]">Думаю...</p>
                  <p className="text-[12px] text-[var(--text-tertiary)]">Если сервер не ответит, запрос остановится автоматически.</p>
                </div>
              </div>
            )}
            {!loading && lastFailedPrompt && (
              <div className="px-4 py-3">
                <button
                  type="button"
                  onClick={() => handleSendMessage(lastFailedPrompt)}
                  className="min-h-11 rounded-[var(--radius-md)] border border-[var(--border-subtle)] px-4 text-[14px] font-medium text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)]"
                >
                  Повторить запрос
                </button>
              </div>
            )}
            <div ref={bottomRef} />
          </div>
        )}
      </div>

      <div className="flex-shrink-0 border-t border-[var(--border-subtle)] bg-[var(--bg-primary)]/95 p-3 pb-[calc(env(safe-area-inset-bottom)+0.75rem)] backdrop-blur-xl">
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
                <button type="button" title="Скоро" className="flex h-11 w-11 items-center justify-center rounded-[var(--radius-md)] text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] transition-colors opacity-50 cursor-not-allowed">
                  <Paperclip size={18} strokeWidth={1.8} />
                </button>
                <button type="button" title="Скоро" className="flex h-11 w-11 items-center justify-center rounded-[var(--radius-md)] text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] transition-colors opacity-50 cursor-not-allowed">
                  <Mic size={18} strokeWidth={1.8} />
                </button>
              </div>
              <button
                type="button"
                onClick={() => handleSendMessage(input)}
                disabled={!input.trim() || loading}
                aria-label="Отправить"
                className={`flex h-11 w-11 items-center justify-center rounded-full transition-all ${
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
