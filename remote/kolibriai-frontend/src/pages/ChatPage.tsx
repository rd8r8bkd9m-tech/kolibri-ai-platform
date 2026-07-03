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
    <div className="flex h-full min-h-0 flex-col bg-[var(--bg-primary)]">
      <div className="flex-1 min-h-0 overflow-y-auto overscroll-contain">
        {messages.length === 0 ? (
          <div className="mx-auto flex min-h-full max-w-[760px] flex-col px-4 pb-6 pt-[clamp(1rem,8dvh,4.5rem)]">
            <div className="flex flex-1 flex-col items-center justify-center pb-8 text-center">
              <div className="relative mb-5">
                <div className="absolute inset-2 rounded-full bg-[var(--accent-teal)]/10 blur-2xl" />
                <MascotAnimation state={focused ? 'ready' : 'idle'} className="relative h-28 w-28 sm:h-32 sm:w-32" alt="Колибри" />
              </div>
              <div className="mb-3 inline-flex items-center gap-2 rounded-[var(--radius-pill)] border border-[var(--border-subtle)] bg-[var(--bg-surface)]/90 px-3 py-1.5 text-[13px] font-medium text-[var(--text-secondary)] shadow-[var(--shadow-sm)] backdrop-blur-xl">
                <span className="h-2 w-2 rounded-full bg-[var(--accent-teal)]" />
                Колибри готов помочь
              </div>
              <h1 className="max-w-[540px] text-[30px] font-semibold leading-tight tracking-normal text-[var(--text-primary)] sm:text-[36px]">
                Чем могу помочь?
              </h1>
              <p className="mt-3 max-w-[460px] text-[16px] leading-6 text-[var(--text-secondary)]">
                Задайте вопрос, создайте смету или попросите подготовить документ.
              </p>

              <div className="mt-6 grid w-full max-w-[560px] gap-2 sm:grid-cols-2">
                {WELCOME_SUGGESTIONS.map((s) => (
                  <button
                    type="button"
                    key={s}
                    onClick={() => handleSendMessage(s)}
                    className="min-h-[54px] rounded-[22px] border border-[var(--border-subtle)] bg-[var(--bg-surface)]/90 px-4 py-3 text-left text-[15px] leading-snug text-[var(--text-primary)] shadow-[var(--shadow-sm)] backdrop-blur-xl transition-colors hover:border-[var(--border-hover)] hover:bg-[var(--bg-hover)]"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <div className="mx-auto max-w-[760px] space-y-1 px-0 py-3 sm:px-4">
            <div className="sticky top-0 z-10 flex justify-end px-4 pb-2 pt-1">
              <button
                type="button"
                onClick={handleNewChat}
                className="flex min-h-10 items-center gap-1.5 rounded-[var(--radius-pill)] border border-white/50 bg-[var(--bg-primary)]/80 px-3 py-1.5 text-[13px] font-medium text-[var(--text-secondary)] shadow-[var(--shadow-sm)] backdrop-blur-xl transition-colors hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)]"
              >
                <Plus size={15} strokeWidth={2} />
                Новый чат
              </button>
            </div>

            {messages.map((msg) => (
              <div
                key={msg.id}
                className={`flex px-4 py-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                {msg.role === 'assistant' ? (
                  <div className="flex w-full max-w-[680px] gap-3">
                    <div className="mt-0.5 flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full bg-[var(--bg-surface)] shadow-[0_4px_16px_rgba(58,186,180,0.16)]">
                      <MascotAnimation state="ready" className="h-8 w-8" decorative />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="mb-1 text-[13px] font-medium text-[var(--text-tertiary)]">Колибри</div>
                      {msg.reasoning && <ReasoningBlock text={msg.reasoning} />}
                      <p className="whitespace-pre-wrap break-words text-[16px] leading-7 text-[var(--text-primary)] [overflow-wrap:anywhere]">
                        {msg.content}
                      </p>
                      {msg.actions && msg.actions.length > 0 && (
                        <div className="mt-4 flex flex-wrap gap-2">
                          {msg.actions.map((action, i) => (
                            <button
                              key={i}
                              type="button"
                              onClick={() => handleAction(action)}
                              className="min-h-11 rounded-[var(--radius-pill)] bg-[var(--accent-teal)] px-4 text-[14px] font-medium text-white shadow-[0_8px_20px_rgba(58,186,180,0.24)] transition-colors hover:bg-[var(--accent-teal-hover)]"
                            >
                              {action.label}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                ) : (
                  <div className="flex max-w-[86%] items-start gap-2 sm:max-w-[72%]">
                    <div className="rounded-[24px] bg-[var(--accent-teal)] px-4 py-3 text-left text-[16px] leading-6 text-white shadow-[0_8px_24px_rgba(58,186,180,0.20)]">
                      <p className="whitespace-pre-wrap break-words [overflow-wrap:anywhere]">{msg.content}</p>
                    </div>
                    <div className="mt-1 hidden h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-[var(--bg-elevated)] text-[var(--text-secondary)] sm:flex">
                      <User size={15} strokeWidth={2} />
                    </div>
                  </div>
                )}
              </div>
            ))}

            {loading && (
              <div className="flex px-4 py-3">
                <div className="flex max-w-[680px] gap-3">
                  <StatusBird state={birdState} size="sm" className="mt-0.5" />
                  <div className="min-w-0 rounded-[24px] bg-[var(--bg-secondary)] px-4 py-3">
                    <p className="text-[16px] font-medium leading-6 text-[var(--text-primary)]">Думаю...</p>
                    <p className="mt-1 text-[13px] leading-5 text-[var(--text-tertiary)]">Если сервер не ответит, запрос остановится автоматически.</p>
                  </div>
                </div>
              </div>
            )}

            {!loading && lastFailedPrompt && (
              <div className="px-4 py-3">
                <button
                  type="button"
                  onClick={() => handleSendMessage(lastFailedPrompt)}
                  className="min-h-11 rounded-[var(--radius-pill)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] px-4 text-[14px] font-medium text-[var(--text-secondary)] shadow-[var(--shadow-sm)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)]"
                >
                  Повторить запрос
                </button>
              </div>
            )}
            <div ref={bottomRef} className="h-4" />
          </div>
        )}
      </div>

      <div className="flex-shrink-0 border-t border-white/40 bg-[var(--bg-primary)]/80 px-3 pb-[calc(env(safe-area-inset-bottom)+0.75rem)] pt-3 backdrop-blur-2xl">
        <div className="mx-auto max-w-[760px]">
          <div
            className={`relative rounded-[28px] border bg-[var(--bg-surface)]/90 shadow-[0_14px_44px_rgba(15,23,42,0.10)] backdrop-blur-xl transition-all duration-200 ${
              focused ? 'border-[var(--accent-teal)] shadow-[0_0_0_3px_rgba(58,186,180,0.12),0_14px_44px_rgba(15,23,42,0.10)]' : 'border-white/70'
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
              className="w-full resize-none bg-transparent px-4 pb-14 pt-4 text-[16px] leading-6 text-[var(--text-primary)] outline-none placeholder:text-[var(--text-tertiary)]"
              style={{ minHeight: 68 }}
            />
            <div className="absolute bottom-2 left-2 right-2 flex items-center justify-between">
              <div className="flex items-center gap-1">
                <button type="button" title="Скоро" className="flex h-11 w-11 cursor-not-allowed items-center justify-center rounded-full text-[var(--text-tertiary)] opacity-55 transition-colors hover:bg-[var(--bg-hover)] hover:text-[var(--text-secondary)]">
                  <Paperclip size={19} strokeWidth={1.8} />
                </button>
                <button type="button" title="Скоро" className="flex h-11 w-11 cursor-not-allowed items-center justify-center rounded-full text-[var(--text-tertiary)] opacity-55 transition-colors hover:bg-[var(--bg-hover)] hover:text-[var(--text-secondary)]">
                  <Mic size={19} strokeWidth={1.8} />
                </button>
              </div>
              <button
                type="button"
                onClick={() => handleSendMessage(input)}
                disabled={!input.trim() || loading}
                aria-label="Отправить"
                className={`flex h-11 w-11 items-center justify-center rounded-full transition-all ${
                  input.trim() && !loading
                    ? 'bg-[var(--accent-teal)] text-white shadow-[0_8px_20px_rgba(58,186,180,0.28)] hover:bg-[var(--accent-teal-hover)]'
                    : 'bg-[var(--bg-elevated)] text-[var(--text-tertiary)]'
                }`}
              >
                <ArrowUp size={18} strokeWidth={2.5} />
              </button>
            </div>
          </div>
          <p className="mt-2 text-center text-[11px] leading-4 text-[var(--text-tertiary)]">AI может ошибаться. Проверяйте важную информацию.</p>
        </div>
      </div>
    </div>
  )
}
