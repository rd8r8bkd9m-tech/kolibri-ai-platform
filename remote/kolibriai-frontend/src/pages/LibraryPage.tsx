import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router'
import { Search, LayoutGrid, List, FileText, Calculator, Table2, Image, BarChart3, Filter } from 'lucide-react'
import { library, type LibraryItem } from '@/lib/api'

const filters = ['Все', 'estimate', 'document', 'pdf', 'table', 'media', 'report']
const filterLabels: Record<string, string> = {
  Все: 'Все', estimate: 'Сметы', document: 'Документы', pdf: 'PDF', table: 'Таблицы', media: 'Медиа', report: 'Отчёты', agent_result: 'AI',
}

const typeIcons: Record<string, { icon: typeof FileText; color: string }> = {
  estimate: { icon: Calculator, color: 'text-[var(--accent-teal)]' },
  document: { icon: FileText, color: 'text-[var(--accent-lavender)]' },
  pdf: { icon: FileText, color: 'text-[var(--status-error)]' },
  table: { icon: Table2, color: 'text-[var(--status-warning)]' },
  media: { icon: Image, color: 'text-[var(--accent-magenta)]' },
  report: { icon: BarChart3, color: 'text-[var(--status-info)]' },
  agent_result: { icon: BarChart3, color: 'text-[var(--accent-teal)]' },
}

export default function LibraryPage() {
  const [activeFilter, setActiveFilter] = useState('Все')
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid')
  const [search, setSearch] = useState('')
  const [items, setItems] = useState<LibraryItem[]>([])
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()

  const handleItemClick = (item: LibraryItem) => {
    if (item.source_type === 'estimate') {
      navigate(`/estimates?edit=${item.source_id}`)
    } else if (item.source_type === 'document') {
      navigate(`/documents?edit=${item.source_id}`)
    }
  }

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await library.list({
        item_type: activeFilter === 'Все' ? undefined : activeFilter,
        search: search || undefined,
        page_size: 50,
      })
      setItems(data.items)
    } catch (e) { console.error('Failed to load library', e) }
    finally { setLoading(false) }
  }, [activeFilter, search])

  useEffect(() => { load() }, [load])

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-[1000px] mx-auto px-4 sm:px-6 py-6">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-[22px] sm:text-[26px] font-semibold text-[var(--text-primary)] tracking-tight">Библиотека</h1>
          <div className="flex items-center gap-1 bg-[var(--bg-elevated)] rounded-[var(--radius-md)] p-0.5">
            <button onClick={() => setViewMode('grid')} className={`p-1.5 rounded-[var(--radius-sm)] transition-colors ${viewMode === 'grid' ? 'bg-white shadow-sm text-[var(--text-primary)]' : 'text-[var(--text-tertiary)]'}`}><LayoutGrid size={16} /></button>
            <button onClick={() => setViewMode('list')} className={`p-1.5 rounded-[var(--radius-sm)] transition-colors ${viewMode === 'list' ? 'bg-white shadow-sm text-[var(--text-primary)]' : 'text-[var(--text-tertiary)]'}`}><List size={16} /></button>
          </div>
        </div>

        <div className="relative mb-4">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-tertiary)]" />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Поиск по библиотеке..."
            className="w-full h-10 pl-9 pr-4 bg-[var(--bg-secondary)] border border-[var(--border-subtle)] rounded-[var(--radius-lg)] text-[14px] text-[var(--text-primary)] placeholder:text-[var(--text-tertiary)] outline-none focus:border-[var(--accent-teal)] focus:ring-2 focus:ring-[var(--accent-teal)]/10 transition-all"
          />
        </div>

        <div className="flex items-center gap-2 mb-6 overflow-x-auto pb-1 scrollbar-hide">
          <Filter size={14} className="text-[var(--text-tertiary)] flex-shrink-0" />
          {filters.map(f => (
            <button
              key={f}
              onClick={() => setActiveFilter(f)}
              className={`px-3 py-1.5 rounded-[var(--radius-pill)] text-[13px] whitespace-nowrap transition-colors ${
                activeFilter === f
                  ? 'bg-[var(--accent-teal)]/10 text-[var(--accent-teal)] font-medium'
                  : 'text-[var(--text-secondary)] hover:bg-[var(--bg-hover)]'
              }`}
            >
              {filterLabels[f] || f}
            </button>
          ))}
        </div>

        {loading ? (
          <div className="text-center py-16 text-[var(--text-tertiary)]">Загрузка...</div>
        ) : items.length === 0 ? (
          <div className="text-center py-16"><p className="text-[14px] text-[var(--text-tertiary)]">Ничего не найдено</p></div>
        ) : viewMode === 'grid' ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {items.map(item => {
              const cfg = typeIcons[item.item_type] || typeIcons.document
              const Icon = cfg.icon
              return (
                <div key={item.id} onClick={() => handleItemClick(item)} className="group p-4 rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] hover:border-[var(--border-hover)] hover:shadow-[var(--shadow-md)] transition-all cursor-pointer">
                  <div className="flex items-start gap-3">
                    <Icon size={20} className={`${cfg.color} flex-shrink-0 mt-0.5`} strokeWidth={1.8} />
                    <div className="min-w-0">
                      <h3 className="text-[14px] font-medium text-[var(--text-primary)] truncate group-hover:text-[var(--accent-teal)] transition-colors">{item.title}</h3>
                      <p className="text-[12px] text-[var(--text-tertiary)] mt-1">{filterLabels[item.item_type] || item.item_type} · {item.client || '—'} · {new Date(item.created_at).toLocaleDateString('ru-RU')}</p>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        ) : (
          <div className="space-y-1">
            {items.map(item => {
              const cfg = typeIcons[item.item_type] || typeIcons.document
              const Icon = cfg.icon
              return (
                <div key={item.id} onClick={() => handleItemClick(item)} className="group flex items-center gap-3 px-4 py-3 rounded-[var(--radius-md)] hover:bg-[var(--bg-hover)] transition-colors cursor-pointer">
                  <Icon size={18} className={`${cfg.color} flex-shrink-0`} strokeWidth={1.8} />
                  <div className="flex-1 min-w-0">
                    <h3 className="text-[14px] text-[var(--text-primary)] truncate group-hover:text-[var(--accent-teal)] transition-colors">{item.title}</h3>
                  </div>
                  <span className="text-[12px] text-[var(--text-tertiary)] hidden sm:block w-24 text-right flex-shrink-0">{filterLabels[item.item_type] || item.item_type}</span>
                  <span className="text-[12px] text-[var(--text-tertiary)] hidden md:block w-32 text-right flex-shrink-0">{item.client || '—'}</span>
                  <span className="text-[12px] text-[var(--text-tertiary)] w-20 text-right flex-shrink-0">{new Date(item.created_at).toLocaleDateString('ru-RU')}</span>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
