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
  const navigate = useNavigate()

  useEffect(() => {
    if (open) {
      setQuery('')
      setResults([])
      setTimeout(() => inputRef.current?.focus(), 100)
    }
  }, [open])

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
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/18 p-0 sm:items-start sm:bg-black/25 sm:p-4 sm:pt-[12vh]" onClick={onClose}>
      <div className="w-full max-w-[560px] overflow-hidden rounded-t-[var(--radius-xl)] border border-[var(--border-subtle)] bg-[var(--bg-primary)] shadow-xl sm:rounded-[var(--radius-xl)]" onClick={e => e.stopPropagation()}>
        <div className="mx-auto mt-2 h-1 w-10 rounded-full bg-[var(--border-hover)] sm:hidden" />
        <div className="flex items-center gap-3 border-b border-[var(--border-subtle)] px-4 py-3">
          <Search size={17} className="flex-shrink-0 text-[var(--text-secondary)]" />
          <div className="min-w-0 flex-1">
            <div className="text-[12px] font-medium text-[var(--text-secondary)] sm:hidden">Поиск</div>
            <input
              ref={inputRef}
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder="Сметы, документы, позиции"
              className="w-full bg-transparent text-[16px] text-[var(--text-primary)] outline-none placeholder:text-[var(--text-tertiary)] sm:text-[14px]"
            />
          </div>
          <button onClick={onClose} className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-[var(--radius-md)] text-[var(--text-tertiary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-secondary)]">
            <X size={16} />
          </button>
        </div>

        <div className="max-h-[min(68dvh,480px)] overflow-y-auto overscroll-contain pb-[env(safe-area-inset-bottom)] sm:max-h-[400px]">
          {loading && <div className="px-4 py-6 text-center text-[13px] text-[var(--text-tertiary)]">Поиск...</div>}

          {!loading && query && results.length === 0 && (
            <div className="px-4 py-6 text-center text-[13px] text-[var(--text-tertiary)]">Ничего не найдено</div>
          )}

          {!loading && results.map((r, i) => (
            <button
              key={`${r.type}-${r.id}-${i}`}
              onClick={() => handleSelect(r)}
              className="flex w-full items-center gap-3 px-4 py-3.5 text-left transition-colors hover:bg-[var(--bg-hover)] sm:py-3"
            >
              {r.type === 'estimate' ? (
                <Calculator size={16} className="text-[var(--accent-teal)] flex-shrink-0" />
              ) : (
                <FileText size={16} className="text-[var(--accent-lavender)] flex-shrink-0" />
              )}
              <div className="flex-1 min-w-0">
                <p className="text-[13px] text-[var(--text-primary)] truncate">{String(r.title || r.name || 'Без названия')}</p>
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
