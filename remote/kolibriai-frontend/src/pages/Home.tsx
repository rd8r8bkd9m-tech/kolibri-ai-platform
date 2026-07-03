import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import { useNavigate } from 'react-router'
import { ArrowUp, Mic, Paperclip, Plus } from 'lucide-react'
import MascotAnimation from '@/components/MascotAnimation'
import { detectChatIntent, shouldShowIntent } from '@/lib/chatIntent'

const STARTER_PROMPTS = [
  'Собери смету на электромонтаж квартиры',
  'Подготовь договор подряда',
  'Разбери продажи за неделю',
]

export default function Home() {
  const [input, setInput] = useState('')
  const [focused, setFocused] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const navigate = useNavigate()
  const intent = useMemo(() => detectChatIntent(input), [input])
  const showIntent = shouldShowIntent(input)

  useEffect(() => {
    const ta = textareaRef.current
    if (!ta) return
    ta.style.height = 'auto'
    ta.style.height = `${Math.min(ta.scrollHeight, 136)}px`
  }, [input])

  const sendPrompt = (prompt: string) => {
    const text = prompt.trim()
    if (!text) return
    sessionStorage.setItem('kolibri_initial_prompt', text)
    setInput('')
    navigate('/chat')
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      sendPrompt(input)
    }
  }

  return (
    <div className="relative flex h-full min-h-0 flex-col overflow-hidden bg-[var(--bg-primary)]">
      <main className="flex min-h-0 flex-1 flex-col items-center px-4 pb-[168px] pt-[clamp(2.25rem,12dvh,6rem)] text-center">
        <div className="relative mb-5">
          <div className="absolute inset-3 rounded-full bg-[var(--accent-teal)]/10 blur-2xl" />
          <MascotAnimation state={focused || showIntent ? 'ready' : 'idle'} className="relative h-[104px] w-[104px] sm:h-32 sm:w-32" alt="Колибри" />
        </div>

        <div className="mb-4 inline-flex min-h-9 items-center rounded-[var(--radius-pill)] border border-[var(--border-subtle)] bg-[var(--bg-surface)]/90 px-4 text-[14px] font-medium text-[var(--text-secondary)] shadow-[0_10px_32px_rgba(15,23,42,0.08)] backdrop-blur-xl">
          Колибри AI · рабочий режим
        </div>

        <h1 className="max-w-[520px] text-[32px] font-semibold leading-[1.08] tracking-normal text-[var(--text-primary)] sm:text-[38px]">
          Чем помочь?
        </h1>
        <p className="mt-3 max-w-[390px] text-[16px] leading-6 text-[var(--text-secondary)] sm:text-[17px]">
          Напишите обычной фразой. Колибри сам поймет, нужен ли расчет, документ, поиск или план.
        </p>

        <section className="mt-6 w-full max-w-[560px]" aria-live="polite">
          {showIntent && !focused ? (
            <div className="rounded-[24px] border border-[var(--border-subtle)] bg-[var(--bg-surface)]/90 p-3 text-left shadow-[0_14px_40px_rgba(15,23,42,0.08)] backdrop-blur-xl">
              <p className="text-[15px] font-semibold leading-5 text-[var(--text-primary)]">{intent.title}</p>
              <p className="mt-1 text-[13px] leading-5 text-[var(--text-secondary)]">{intent.subtitle}</p>
              <div className="mt-3 grid grid-cols-3 gap-1.5">
                {intent.directions.map((direction) => (
                  <button
                    type="button"
                    key={direction.label}
                    onClick={() => setInput((current) => `${current.trim()} ${direction.label.toLowerCase()}`.trim())}
                    className="min-h-[50px] rounded-[16px] border border-white/70 bg-[var(--bg-surface)]/85 px-2 py-1.5 text-left transition-colors hover:border-[var(--border-hover)] hover:bg-[var(--bg-surface)]"
                  >
                    <span className="block truncate text-[12px] font-medium leading-4 text-[var(--text-primary)]">{direction.label}</span>
                    <span className="block truncate text-[11px] leading-4 text-[var(--text-tertiary)]">{direction.detail}</span>
                  </button>
                ))}
              </div>
            </div>
          ) : !showIntent ? (
            <div className="flex flex-wrap justify-center gap-2">
              {STARTER_PROMPTS.map((prompt) => (
                <button
                  type="button"
                  key={prompt}
                  onClick={() => sendPrompt(prompt)}
                  className="rounded-[var(--radius-pill)] border border-[var(--border-subtle)] bg-[var(--bg-surface)]/85 px-3.5 py-2 text-[14px] leading-5 text-[var(--text-secondary)] shadow-[var(--shadow-sm)] backdrop-blur-xl transition-colors hover:border-[var(--border-hover)] hover:text-[var(--text-primary)]"
                >
                  {prompt}
                </button>
              ))}
            </div>
          ) : null}
        </section>
      </main>

      <footer className="absolute inset-x-0 bottom-0 z-30 border-t border-white/40 bg-[var(--bg-primary)]/72 px-3 pb-[calc(env(safe-area-inset-bottom)+0.75rem)] pt-3 backdrop-blur-2xl">
        <div className="mx-auto max-w-[760px]">
          {showIntent && focused && (
            <div className="mb-2 rounded-[24px] border border-[var(--border-subtle)] bg-[var(--bg-surface)]/90 p-3 text-left shadow-[0_12px_34px_rgba(15,23,42,0.08)] backdrop-blur-xl" aria-live="polite">
              <p className="text-[14px] font-semibold leading-5 text-[var(--text-primary)]">{intent.title}</p>
              <p className="mt-0.5 text-[12px] leading-4 text-[var(--text-secondary)]">{intent.subtitle}</p>
              <div className="mt-2 grid grid-cols-3 gap-1.5">
                {intent.directions.map((direction) => (
                  <button
                    type="button"
                    key={direction.label}
                    onMouseDown={(event) => event.preventDefault()}
                    onClick={() => setInput((current) => `${current.trim()} ${direction.label.toLowerCase()}`.trim())}
                    className="min-h-[48px] rounded-[16px] border border-white/70 bg-[var(--bg-surface)]/85 px-2 py-1.5 text-left transition-colors hover:border-[var(--border-hover)] hover:bg-[var(--bg-surface)]"
                  >
                    <span className="block truncate text-[12px] font-medium leading-4 text-[var(--text-primary)]">{direction.label}</span>
                    <span className="block truncate text-[11px] leading-4 text-[var(--text-tertiary)]">{direction.detail}</span>
                  </button>
                ))}
              </div>
            </div>
          )}
          <div
            className={`relative rounded-[30px] border bg-[var(--bg-surface)]/92 shadow-[0_18px_50px_rgba(15,23,42,0.12)] backdrop-blur-2xl transition-all duration-200 ${
              focused
                ? 'border-[var(--accent-teal)] shadow-[0_0_0_3px_rgba(58,186,180,0.12),0_18px_50px_rgba(15,23,42,0.12)]'
                : 'border-white/70'
            }`}
          >
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onFocus={() => setFocused(true)}
              onBlur={() => setFocused(false)}
              onKeyDown={handleKeyDown}
              placeholder="Спросите Колибри..."
              rows={1}
              className="w-full resize-none bg-transparent px-4 pb-14 pt-4 text-[17px] leading-6 text-[var(--text-primary)] outline-none placeholder:text-[var(--text-tertiary)]"
              style={{ minHeight: 72 }}
            />
            <div className="absolute bottom-2 left-2 right-2 flex items-center justify-between">
              <div className="flex items-center gap-1">
                <button type="button" title="Добавить" className="flex h-11 w-11 cursor-not-allowed items-center justify-center rounded-full text-[var(--text-tertiary)] opacity-55">
                  <Plus size={19} strokeWidth={1.8} />
                </button>
                <button type="button" title="Файл" className="flex h-11 w-11 cursor-not-allowed items-center justify-center rounded-full text-[var(--text-tertiary)] opacity-55">
                  <Paperclip size={19} strokeWidth={1.8} />
                </button>
                <button type="button" title="Голос" className="flex h-11 w-11 cursor-not-allowed items-center justify-center rounded-full text-[var(--text-tertiary)] opacity-55">
                  <Mic size={19} strokeWidth={1.8} />
                </button>
              </div>
              <button
                type="button"
                onClick={() => sendPrompt(input)}
                disabled={!input.trim()}
                aria-label="Отправить"
                className={`flex h-11 w-11 items-center justify-center rounded-full transition-all ${
                  input.trim()
                    ? 'bg-[var(--accent-teal)] text-white shadow-[0_8px_22px_rgba(58,186,180,0.30)] hover:bg-[var(--accent-teal-hover)]'
                    : 'bg-[var(--bg-elevated)] text-[var(--text-tertiary)]'
                }`}
              >
                <ArrowUp size={18} strokeWidth={2.5} />
              </button>
            </div>
          </div>
          <p className="mt-2 text-center text-[11px] leading-4 text-[var(--text-tertiary)]">AI может ошибаться. Проверяйте важную информацию.</p>
        </div>
      </footer>
    </div>
  )
}
