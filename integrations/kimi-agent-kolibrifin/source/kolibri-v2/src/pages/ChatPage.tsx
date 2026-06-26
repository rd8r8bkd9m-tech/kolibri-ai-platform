import { useState, useRef, useEffect } from 'react'
import { useSearchParams } from 'react-router'
/* framer-motion removed */
import { Paperclip, ArrowUp, Mic, User } from 'lucide-react'

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
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
  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const [searchParams] = useSearchParams()
  const prompt = searchParams.get('q') || ''

  useEffect(() => {
    if (prompt) {
      handleSendMessage(prompt)
    }
  }, [prompt])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSendMessage = (text: string) => {
    if (!text.trim()) return
    const userMsg: Message = { id: Date.now().toString(), role: 'user', content: text, timestamp: new Date() }
    const assistantMsg: Message = {
      id: (Date.now() + 1).toString(),
      role: 'assistant',
      content: generateResponse(text),
      timestamp: new Date(),
    }
    setMessages((prev) => [...prev, userMsg, assistantMsg])
    setInput('')
  }

  const generateResponse = (text: string): string => {
    if (text.toLowerCase().includes('смет')) {
      return 'Я создам смету на электромонтажные работы. Вот структура:\n\n**Раздел 1: Электромонтажные работы**\n- Прокладка кабеля ВВГнг 3x2.5 — 150 м × 85.50 ₽ = 12 825 ₽\n- Монтаж розетки — 25 шт × 450 ₽ = 11 250 ₽\n- Установка автомата 16А — 12 шт × 320 ₽ = 3 840 ₽\n- Сборка электрощита — 1 компл × 8 500 ₽ = 8 500 ₽\n\n**Итого: 36 415 ₽**\n\nНажмите «Открыть в редакторе», чтобы изменить позиции, добавить разделы или скорректировать цены.'
    }
    if (text.toLowerCase().includes('договор')) {
      return 'Готовлю договор подряда. Какие параметры нужно указать?\n\n- Заказчик: _______\n- Исполнитель: _______\n- Предмет договора: _______\n- Срок выполнения: _______\n- Стоимость: _______\n\nЗаполните данные, и я сгенерирую полноценный документ с правильной структурой.'
    }
    return 'Понял ваш запрос. Я могу помочь с:\n\n• Созданием смет и калькуляцией\n• Подготовкой документов (договоры, акты, КП)\n• Анализом данных и отчётов\n• Генерацией кода и технических заданий\n\nЧто именно нужно сделать?'
  }

  return (
    <div className="flex flex-col h-full">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full px-4">
            <img src="/kolibri-bird.png" alt="" className="w-12 h-12 object-contain mb-4 opacity-60" />
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
                    <img src="/kolibri-bird.png" alt="" className="w-7 h-7 object-contain" />
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-[14px] text-[var(--text-primary)] leading-relaxed whitespace-pre-wrap">{msg.content}</p>
                </div>
              </div>
            ))}
            <div ref={bottomRef} />
          </div>
        )}
      </div>

      {/* Input */}
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
              style={{ minHeight: 56, maxHeight: 160 }}
            />
            <div className="absolute bottom-2 left-2 right-2 flex items-center justify-between">
              <div className="flex items-center gap-1">
                <button className="w-8 h-8 flex items-center justify-center rounded-[var(--radius-md)] text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] transition-colors">
                  <Paperclip size={18} strokeWidth={1.8} />
                </button>
                <button className="w-8 h-8 flex items-center justify-center rounded-[var(--radius-md)] text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] transition-colors">
                  <Mic size={18} strokeWidth={1.8} />
                </button>
              </div>
              <button
                onClick={() => handleSendMessage(input)}
                disabled={!input.trim()}
                className={`w-8 h-8 flex items-center justify-center rounded-full transition-all ${
                  input.trim() ? 'bg-[var(--accent-teal)] text-white hover:bg-[var(--accent-teal-hover)]' : 'bg-[var(--bg-elevated)] text-[var(--text-tertiary)]'
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
