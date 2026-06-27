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
    <div className="fixed inset-0 bg-black/30 z-50 flex items-start justify-center pt-[15vh] p-4" onClick={onClose}>
      <div className="bg-[var(--bg-primary)] rounded-[var(--radius-xl)] shadow-xl max-w-[560px] w-full overflow-hidden" onClick={e => e.stopPropagation()}>
        <div className="flex items-center gap-3 px-4 py-3 border-b border-[var(--border-subtle)]">
          <Search size={16} className="text-[var(--text-tertiary)] flex-shrink-0" />
          <input
            ref={inputRef}
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="Поиск по сметам, документам, позициям..."
            className="flex-1 text-[14px] bg-transparent outline-none text-[var(--text-primary)] placeholder:text-[var(--text-tertiary)]"
          />
          <button onClick={onClose} className="w-6 h-6 flex items-center justify-center rounded text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]">
            <X size={16} />
          </button>
        </div>

        <div className="max-h-[400px] overflow-y-auto">
          {loading && <div className="px-4 py-6 text-center text-[13px] text-[var(--text-tertiary)]">Поиск...</div>}

          {!loading && query && results.length === 0 && (
            <div className="px-4 py-6 text-center text-[13px] text-[var(--text-tertiary)]">Ничего не найдено</div>
          )}

          {!loading && results.map((r, i) => (
            <button
              key={`${r.type}-${r.id}-${i}`}
              onClick={() => handleSelect(r)}
              className="w-full flex items-center gap-3 px-4 py-3 hover:bg-[var(--bg-hover)] transition-colors text-left"
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
