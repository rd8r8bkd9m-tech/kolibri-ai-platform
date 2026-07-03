import { useState, useRef, useEffect } from 'react'
import { useNavigate, useOutletContext } from 'react-router'
import {
  Paperclip,
  ArrowUp,
  Mic,
  Plus,
  Compass,
  Calculator,
  FileText,
  Bot,
  MessageSquare,
  Library,
  Search,
  Settings,
  ChevronRight,
} from 'lucide-react'
import StatusBird from '@/components/StatusBird'
import MascotAnimation from '@/components/MascotAnimation'
import { estimates, documents, agents, library, type Estimate, type Document, type LibraryItem, type Agent } from '@/lib/api'
import type { LayoutOutletContext } from '@/components/Layout'
import { formatDate, formatCurrency } from '@/lib/utils'

const quickActions = [
  'Создать смету на электромонтаж',
  'Написать договор подряда',
  'Сгенерировать отчёт',
  'Проанализировать данные',
]

type Module = {
  id: 'chat' | 'estimates' | 'documents' | 'agents' | 'library' | 'settings' | 'search'
  label: string
  icon: typeof MessageSquare
  description: string
  route: '/chat' | '/estimates' | '/documents' | '/agents' | '/library' | '/settings' | 'search'
}

const modules: Module[] = [
  {
    id: 'chat',
    label: 'Чат',
    icon: MessageSquare,
    description: 'Веди диалог и запускай действия сразу из ответа',
    route: '/chat',
  },
  {
    id: 'estimates',
    label: 'Сметы',
    icon: Calculator,
    description: 'Скидки, расчёты, экспорт, версия в рабочем режиме',
    route: '/estimates',
  },
  {
    id: 'documents',
    label: 'Документы',
    icon: FileText,
    description: 'Редакторы и шаблоны в связке со сметами',
    route: '/documents',
  },
  {
    id: 'agents',
    label: 'Агенты',
    icon: Bot,
    description: 'Управление задачами и статуса выполнения',
    route: '/agents',
  },
  {
    id: 'library',
    label: 'Библиотека',
    icon: Library,
    description: 'История проектов и подборки материалов',
    route: '/library',
  },
  {
    id: 'settings',
    label: 'Настройки',
    icon: Settings,
    description: 'Профиль, тема, оповещения, безопасность',
    route: '/settings',
  },
  { 
    id: 'search',
    label: 'Поиск',
    icon: Search,
    description: 'Найди сметы, документы и шаблоны',
    route: 'search',
  },
]

export default function Home() {
  const [input, setInput] = useState('')
  const [focused, setFocused] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const navigate = useNavigate()

  const [recentEstimates, setRecentEstimates] = useState<Estimate[]>([])
  const [recentDocuments, setRecentDocuments] = useState<Document[]>([])
  const [recentLibrary, setRecentLibrary] = useState<LibraryItem[]>([])
  const [recentAgents, setRecentAgents] = useState<Agent[]>([])
  const [stats, setStats] = useState({ estimates: 0, documents: 0, agents: 0 })
  const [loading, setLoading] = useState(true)
  const layout = useOutletContext<LayoutOutletContext | null>()
  const openGlobalSearch = layout?.openSearch ?? (() => navigate('/library'))

  const adaptiveDirection = (() => {
    if (loading) {
      return {
        label: 'Синхронизация',
        title: 'Проверяю рабочую область',
        detail: 'Подтягиваю сметы, документы и агентов.',
        action: 'Открыть чат',
        route: '/chat',
      }
    }
    if (recentEstimates.length > 0) {
      return {
        label: 'Рабочее продолжение',
        title: 'Продолжите последнюю смету',
        detail: `${recentEstimates[0].title} · ${formatCurrency(recentEstimates[0].total)}`,
        action: 'Открыть сметы',
        route: '/estimates',
      }
    }
    if (recentDocuments.length > 0) {
      return {
        label: 'Документы',
        title: 'Вернитесь к последнему документу',
        detail: recentDocuments[0].title,
        action: 'Открыть документы',
        route: '/documents',
      }
    }
    if (stats.agents > 0) {
      return {
        label: 'Агенты',
        title: 'Проверьте активные задачи',
        detail: 'Есть агенты, по которым можно сверить состояние работ.',
        action: 'Открыть агентов',
        route: '/agents',
      }
    }
    return {
      label: 'Первый шаг',
      title: 'Опишите задачу одним сообщением',
      detail: 'Колибри предложит следующее действие и сохранит результат в рабочем контуре.',
      action: 'Начать чат',
      route: '/chat',
    }
  })()

  useEffect(() => {
    let alive = true

    const load = async () => {
      try {
        const [est, doc, ag, lib] = await Promise.all([
          estimates.list({ page_size: 5 }),
          documents.list({ page_size: 5 }),
          agents.list({ page_size: 5 }),
          library.list({ page_size: 5 }),
        ])
        if (!alive) return

        setRecentEstimates(est.items)
        setRecentDocuments(doc.items)
        setRecentAgents(ag.items)
        setRecentLibrary(lib.items)
        setStats({ estimates: est.total, documents: doc.total, agents: ag.items.length })
      } catch {
        // no-op
      } finally {
        if (alive) setLoading(false)
      }
    }

    load()
    return () => { alive = false }
  }, [])

  const navigateTo = (path: string) => {
    if (path === 'search') {
      openGlobalSearch()
      return
    }
    navigate(path)
  }

  const handleSend = () => {
    if (!input.trim()) return
    const prompt = input.trim()
    setInput('')
    sessionStorage.setItem('kolibri_initial_prompt', prompt)
    navigate('/chat')
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleQuickPrompt = (prompt: string) => {
    sessionStorage.setItem('kolibri_initial_prompt', prompt)
    navigate('/chat')
  }

  const moduleById = (id: string) => {
    if (id === 'estimates') {
      if (!recentEstimates.length) return 'Пока нет сохранённых смет'
      return recentEstimates[0]?.title || 'Последняя смета'
    }
    if (id === 'documents') {
      if (!recentDocuments.length) return 'Пока нет документов'
      return recentDocuments[0]?.title || 'Последний документ'
    }
    if (id === 'agents') {
      if (!recentAgents.length) return 'Сейчас нет активных агентов'
      return `${recentAgents[0]?.name || 'Агент'} · ${recentAgents[0]?.status || 'неизвестен'}`
    }
    if (id === 'library') {
      if (!recentLibrary.length) return 'Сейчас библиотека пуста'
      return recentLibrary[0]?.title || 'Последний элемент'
    }
    if (id === 'search') {
      return `Смет: ${stats.estimates} · Документов: ${stats.documents}`
    }
    return 'Откройте поток рабочего режима'
  }

  return (
    <div className="min-h-[100dvh]">
      {/* Desktop version unchanged */}
      <div className="hidden md:block">
        <div className="flex flex-col items-center min-h-[100dvh] px-4 pt-[12dvh] pb-20 sm:pt-[15vh] relative">
          <div className="mb-6 opacity-0 animate-wakeUp">
            <StatusBird state={focused ? 'ready' : 'idle'} size="lg" />
          </div>

          <h1 className="text-[28px] sm:text-[32px] font-semibold text-[var(--text-primary)] tracking-tight mb-8 animate-slideUp animation-delay-100">
            Чем могу помочь?
          </h1>

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

            <div className="flex flex-wrap justify-center gap-2 mt-4">
              {quickActions.map((action) => (
                <button
                  key={action}
                  onClick={() => handleQuickPrompt(action)}
                  className="px-3 py-1.5 rounded-[var(--radius-pill)] border border-[var(--border-subtle)] text-[13px] text-[var(--text-secondary)] hover:border-[var(--border-hover)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-hover)] transition-colors"
                >
                  {action}
                </button>
              ))}
            </div>

            <button
              type="button"
              onClick={() => navigate(adaptiveDirection.route)}
              className="mt-5 flex w-full items-start gap-3 rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] px-4 py-3 text-left shadow-[var(--shadow-sm)] transition-all hover:border-[var(--border-hover)] hover:bg-[var(--bg-hover)]"
            >
              <span className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-[var(--radius-md)] bg-[var(--accent-teal)]/10 text-[var(--accent-teal)]">
                <Compass size={19} strokeWidth={1.8} />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block text-[11px] font-medium uppercase tracking-wide text-[var(--text-tertiary)]">{adaptiveDirection.label}</span>
                <span className="mt-0.5 block text-[14px] font-semibold text-[var(--text-primary)]">{adaptiveDirection.title}</span>
                <span className="mt-0.5 block truncate text-[13px] text-[var(--text-secondary)]">{adaptiveDirection.detail}</span>
              </span>
              <span className="mt-1 shrink-0 text-[13px] font-medium text-[var(--accent-teal)]">{adaptiveDirection.action}</span>
            </button>
          </div>

          {(stats.estimates > 0 || recentEstimates.length > 0) && (
            <div className="w-full max-w-[680px] mt-10 animate-slideUp animation-delay-300">
              <div className="grid grid-cols-3 gap-3 mb-6">
                {[
                  { icon: Calculator, label: 'Смет', value: stats.estimates, color: 'var(--accent-teal)' },
                  { icon: FileText, label: 'Документов', value: stats.documents, color: 'var(--accent-lavender)' },
                  { icon: Bot, label: 'Агентов', value: stats.agents, color: 'var(--accent-amber)' },
                ].map((s) => (
                  <button
                    key={s.label}
                    onClick={() => navigate(s.label === 'Смет' ? '/estimates' : s.label === 'Документов' ? '/documents' : '/agents')}
                    className="flex items-center gap-3 p-3 rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] hover:border-[var(--border-hover)] hover:shadow-[var(--shadow-sm)] transition-all"
                  >
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

              {recentEstimates.length > 0 && (
                <div>
                  <p className="text-[11px] font-medium text-[var(--text-tertiary)] uppercase tracking-wider mb-2">Недавние сметы</p>
                  <div className="space-y-1.5">
                    {recentEstimates.map((est) => (
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

          <p className="absolute bottom-4 text-[11px] text-[var(--text-tertiary)] animate-slideUp animation-delay-400">
            AI генерирует содержимое. Проверяйте важную информацию.
          </p>
        </div>
      </div>

      {/* Mobile single-screen experience */}
      <div className="md:hidden min-h-[100dvh] bg-[var(--bg-primary)] pb-[calc(env(safe-area-inset-bottom)+1.5rem)]">
        <section className="px-4 pt-8 pb-4">
          <div className="mb-5 flex justify-center">
            <div className="relative">
              <div className="absolute inset-2 rounded-full bg-[var(--accent-teal)]/10 blur-2xl" />
              <MascotAnimation state={focused ? 'ready' : 'idle'} className="relative h-28 w-28" alt="Колибри" />
            </div>
          </div>
          <h1 className="text-center text-[32px] leading-tight font-semibold tracking-normal text-[var(--text-primary)]">Чем могу помочь?</h1>
          <p className="mx-auto mt-2 max-w-[340px] text-center text-[16px] leading-6 text-[var(--text-secondary)]">
            Колибри умеет вести диалог, находить материалы и запускать рабочие действия.
          </p>

          <div
            className={`relative mt-5 rounded-[28px] border bg-[var(--bg-surface)]/90 shadow-[0_14px_44px_rgba(15,23,42,0.10)] backdrop-blur-xl transition-all duration-200 ${
              focused
                ? 'border-[var(--accent-teal)] shadow-[0_0_0_3px_rgba(58,186,180,0.12),0_14px_44px_rgba(15,23,42,0.10)]'
                : 'border-white/70'
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
              className="w-full resize-none bg-transparent px-4 pb-14 pt-4 text-[18px] leading-relaxed text-[var(--text-primary)] outline-none placeholder:text-[var(--text-tertiary)]"
              style={{ minHeight: 68, maxHeight: 180 }}
            />
            <div className="absolute bottom-2 left-2 right-2 flex items-center justify-between">
              <div className="flex items-center gap-1">
                <button type="button" title="Скоро" className="flex h-10 w-10 cursor-not-allowed items-center justify-center rounded-full text-[var(--text-tertiary)] opacity-55">
                  <Plus size={20} strokeWidth={1.8} />
                </button>
                <button type="button" title="Скоро" className="flex h-10 w-10 cursor-not-allowed items-center justify-center rounded-full text-[var(--text-tertiary)] opacity-55">
                  <Paperclip size={20} strokeWidth={1.8} />
                </button>
                <button type="button" title="Скоро" className="flex h-10 w-10 cursor-not-allowed items-center justify-center rounded-full text-[var(--text-tertiary)] opacity-55">
                  <Mic size={20} strokeWidth={1.8} />
                </button>
              </div>
              <button
                type="button"
                onClick={handleSend}
                disabled={!input.trim()}
                aria-label="Отправить"
                className={`flex h-10 w-10 items-center justify-center rounded-full transition-all ${
                  input.trim()
                    ? 'bg-[var(--accent-teal)] text-white shadow-[0_8px_20px_rgba(58,186,180,0.28)]'
                    : 'bg-[var(--bg-elevated)] text-[var(--text-tertiary)]'
                }`}
              >
                <ArrowUp size={19} strokeWidth={2.5} />
              </button>
            </div>
          </div>

          <div className="mt-3 flex flex-wrap gap-2">
            {quickActions.map((action) => (
              <button
                type="button"
                key={action}
                onClick={() => handleQuickPrompt(action)}
                className="rounded-[var(--radius-pill)] border border-[var(--border-subtle)] bg-[var(--bg-surface)]/90 px-3.5 py-2 text-[15px] text-[var(--text-secondary)] shadow-[var(--shadow-sm)]"
              >
                {action}
              </button>
            ))}
          </div>
          <p className="mt-3 text-[13px] text-[var(--text-tertiary)]">AI может ошибаться — проверяйте финальную информацию.</p>

          <button
            type="button"
            onClick={() => navigate(adaptiveDirection.route)}
            className="mt-4 flex w-full items-start gap-3 rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-3.5 text-left shadow-[var(--shadow-sm)]"
          >
            <span className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-[var(--radius-md)] bg-[var(--accent-teal)]/10 text-[var(--accent-teal)]">
              <Compass size={19} strokeWidth={1.8} />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block text-[12px] font-medium uppercase tracking-wide text-[var(--text-tertiary)]">{adaptiveDirection.label}</span>
              <span className="mt-0.5 block text-[16px] font-semibold leading-tight text-[var(--text-primary)]">{adaptiveDirection.title}</span>
              <span className="mt-1 block text-[14px] leading-snug text-[var(--text-secondary)]">{adaptiveDirection.detail}</span>
              <span className="mt-2 block text-[14px] font-medium text-[var(--accent-teal)]">{adaptiveDirection.action}</span>
            </span>
          </button>
        </section>

        <section className="px-4">
          <div className="grid grid-cols-3 gap-2">
            {[
              { icon: Calculator, label: 'Смет', value: stats.estimates, color: 'var(--accent-teal)' },
              { icon: FileText, label: 'Док', value: stats.documents, color: 'var(--accent-lavender)' },
              { icon: Bot, label: 'Агент', value: stats.agents, color: 'var(--accent-amber)' },
            ].map((item) => {
              const Icon = item.icon
              return (
                <div key={item.label} className="rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-3">
                  <div
                    className="w-9 h-9 rounded-[var(--radius-md)] flex items-center justify-center mb-2"
                    style={{ background: `${item.color}15`, color: item.color }}
                  >
                    <Icon size={18} strokeWidth={1.8} />
                  </div>
                  <p className="text-[20px] font-semibold leading-none text-[var(--text-primary)]">
                    {loading ? '—' : item.value}
                  </p>
                  <p className="text-[13px] text-[var(--text-tertiary)] mt-1">{item.label}</p>
                </div>
              )
            })}
          </div>
        </section>

        <section className="px-4 mt-3 space-y-2">
          {modules.map((module) => {
            const ModuleIcon = module.icon
            return (
              <button
                type="button"
                key={module.id}
                onClick={() => navigateTo(module.route)}
                className="w-full rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-3.5 text-left"
              >
                <div className="flex items-start gap-3">
                  <div className="w-11 h-11 rounded-[var(--radius-md)] bg-[var(--bg-elevated)] text-[var(--text-secondary)] flex items-center justify-center flex-shrink-0">
                    <ModuleIcon size={20} strokeWidth={1.8} />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-[17px] font-medium text-[var(--text-primary)]">{module.label}</p>
                    <p className="text-[14px] text-[var(--text-tertiary)] mt-0.5 leading-snug">{module.description}</p>
                    <p className="text-[14px] text-[var(--text-secondary)] mt-1.5">
                      {module.id === 'chat'
                        ? 'Открыть диалог'
                        : moduleById(module.id === 'search' ? 'search' : module.id)}
                    </p>
                  </div>
                  <ChevronRight size={19} className="text-[var(--text-tertiary)] mt-1" />
                </div>
              </button>
            )
          })}
        </section>

        {(!loading && recentEstimates.length > 0) && (
          <section className="px-4 mt-3 space-y-1.5">
            <p className="text-[13px] font-medium text-[var(--text-tertiary)] uppercase tracking-wider">Недавние сметы</p>
            {recentEstimates.map((est) => (
              <button
                key={est.id}
                onClick={() => navigate(`/estimates?edit=${est.id}`)}
                className="w-full flex items-center justify-between px-3.5 py-3 rounded-[var(--radius-md)] border border-[var(--border-subtle)] bg-[var(--bg-surface)]"
              >
                <div className="min-w-0">
                  <p className="text-[15px] text-[var(--text-primary)] truncate">{est.title}</p>
                  <p className="text-[13px] text-[var(--text-tertiary)] truncate">{est.client || '—'} · {formatDate(est.created_at)}</p>
                </div>
                <span className="text-[15px] font-semibold text-[var(--text-primary)] ml-3">{formatCurrency(est.total)}</span>
              </button>
            ))}
          </section>
        )}
      </div>
    </div>
  )
}
