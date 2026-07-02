import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router'
import { Search, FileText, Calculator, X } from 'lucide-react'
import { search, type SearchResult } from '@/lib/api'

interface SearchModalProps {
  open: boolean
  onClose: () => void
}

export default function SearchModal({ open, onClose }: SearchModalProps) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchResult[]>([])
  const [loading, setLoading] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const dialogRef = useRef<HTMLDivElement>(null)
  const restoreFocusRef = useRef<HTMLElement | null>(null)
  const navigate = useNavigate()

  useEffect(() => {
    if (open) {
      restoreFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null
      setQuery('')
      setResults([])
      setTimeout(() => inputRef.current?.focus(), 100)
    } else {
      restoreFocusRef.current?.focus()
      restoreFocusRef.current = null
    }
  }, [open])

  useEffect(() => {
    if (!open) return
    const previousOverflow = document.body.style.overflow
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        onClose()
      }
      if (event.key !== 'Tab') return
      const focusables = Array.from(dialogRef.current?.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
      ) || []).filter(el => !el.hasAttribute('disabled') && el.tabIndex !== -1)
      if (focusables.length === 0) return
      const first = focusables[0]
      const last = focusables[focusables.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }
    document.body.style.overflow = 'hidden'
    window.addEventListener('keydown', handleKeyDown)
    return () => {
      document.body.style.overflow = previousOverflow
      window.removeEventListener('keydown', handleKeyDown)
    }
  }, [onClose, open])

  useEffect(() => {
    if (!query.trim()) {
      setResults([])
      return
    }
    const timer = setTimeout(async () => {
      setLoading(true)
      try {
        const res = await search.all(query, ['estimates', 'documents', 'positions'], 10)
        setResults(res.results)
      } catch { setResults([]) }
      finally { setLoading(false) }
    }, 300)
    return () => clearTimeout(timer)
  }, [query])

  const handleSelect = (r: SearchResult) => {
    if (r.type === 'estimate') navigate(`/estimates?edit=${r.id}`)
    else if (r.type === 'document') navigate(`/documents?edit=${r.id}`)
    onClose()
  }

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-[70] flex items-end justify-center bg-black/35 p-0 sm:items-start sm:p-4 sm:pt-[15vh]"
      onClick={onClose}
      role="presentation"
    >
      <div
        ref={dialogRef}
        className="max-h-[min(82dvh,640px)] w-full overflow-hidden rounded-t-[28px] border border-white/20 bg-[var(--bg-primary)]/95 shadow-2xl backdrop-blur-xl sm:max-w-[560px] sm:rounded-[var(--radius-xl)]"
        onClick={e => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label="Поиск"
      >
        <div className="mx-auto mt-2 h-1 w-10 rounded-full bg-[var(--border-hover)] sm:hidden" />
        <div className="flex items-center gap-3 border-b border-[var(--border-subtle)] px-4 py-3">
          <Search size={16} className="text-[var(--text-tertiary)] flex-shrink-0" />
          <input
            ref={inputRef}
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="Поиск"
            className="min-h-11 min-w-0 flex-1 bg-transparent text-[14px] text-[var(--text-primary)] outline-none placeholder:text-[var(--text-tertiary)]"
          />
          <button onClick={onClose} className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[var(--radius-md)] text-[var(--text-tertiary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-secondary)]" aria-label="Закрыть поиск">
            <X size={16} />
          </button>
        </div>

        <div className="max-h-[calc(min(82dvh,640px)-74px)] overflow-y-auto overscroll-contain pb-[env(safe-area-inset-bottom)]">
          {loading && <div className="px-4 py-6 text-center text-[13px] text-[var(--text-tertiary)]">Поиск...</div>}

          {!loading && query && results.length === 0 && (
            <div className="px-4 py-6 text-center text-[13px] text-[var(--text-tertiary)]">Ничего не найдено</div>
          )}

          {!loading && results.map((r, i) => (
            <button
              key={`${r.type}-${r.id}-${i}`}
              onClick={() => handleSelect(r)}
              className="flex min-h-[56px] w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-[var(--bg-hover)]"
            >
              {r.type === 'estimate' ? (
                <Calculator size={16} className="text-[var(--accent-teal)] flex-shrink-0" />
              ) : (
                <FileText size={16} className="text-[var(--accent-lavender)] flex-shrink-0" />
              )}
              <div className="flex-1 min-w-0">
                <p className="text-[13px] text-[var(--text-primary)] break-words [overflow-wrap:anywhere]">{String(r.title || r.name || 'Без названия')}</p>
                <p className="text-[11px] text-[var(--text-tertiary)]">{r.type === 'estimate' ? 'Смета' : r.type === 'document' ? 'Документ' : 'Позиция'}</p>
              </div>
            </button>
          ))}

          {!query && (
            <div className="px-4 py-6 text-center text-[13px] text-[var(--text-tertiary)]">
              Начните вводить для поиска
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
