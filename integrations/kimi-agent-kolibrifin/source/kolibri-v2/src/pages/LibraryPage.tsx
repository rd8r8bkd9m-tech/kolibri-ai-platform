import { useState } from 'react'
import { Search, LayoutGrid, List, FileText, Calculator, Table2, Image, BarChart3, Filter } from 'lucide-react'

const filters = ['Все', 'Сметы', 'Документы', 'PDF', 'Таблицы', 'Отчёты']

const items = [
  { id: '1', title: 'Смета на электромонтаж дома 120 м²', type: 'Смета', date: '25 июн 2026', client: 'Иванов И.И.', icon: Calculator, color: 'text-[var(--accent-teal)]' },
  { id: '2', title: 'Договор подряда №45/2026', type: 'Документ', date: '24 июн 2026', client: 'ООО СтройПро', icon: FileText, color: 'text-[var(--accent-lavender)]' },
  { id: '3', title: 'Анализ продаж Q2 2026', type: 'Отчёт', date: '22 июн 2026', client: 'Внутренний', icon: BarChart3, color: 'text-[var(--status-info)]' },
  { id: '4', title: 'Смета на ремонт офиса', type: 'Смета', date: '20 июн 2026', client: 'ООО ТехноСервис', icon: Calculator, color: 'text-[var(--accent-teal)]' },
  { id: '5', title: 'Коммерческое предложение', type: 'Документ', date: '18 июн 2026', client: 'Петров С.А.', icon: FileText, color: 'text-[var(--accent-lavender)]' },
  { id: '6', title: 'Прайс-лист материалов', type: 'Таблица', date: '15 июн 2026', client: '—', icon: Table2, color: 'text-[var(--status-warning)]' },
  { id: '7', title: 'Фото объекта', type: 'Медиа', date: '12 июн 2026', client: 'Иванов И.И.', icon: Image, color: 'text-[var(--accent-magenta)]' },
  { id: '8', title: 'Акт выполненных работ', type: 'Документ', date: '10 июн 2026', client: 'ООО СтройПро', icon: FileText, color: 'text-[var(--accent-lavender)]' },
]

export default function LibraryPage() {
  const [activeFilter, setActiveFilter] = useState('Все')
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid')
  const [search, setSearch] = useState('')

  const filtered = items.filter(i => {
    const matchFilter = activeFilter === 'Все' || i.type === activeFilter
    const matchSearch = !search || i.title.toLowerCase().includes(search.toLowerCase()) || i.client.toLowerCase().includes(search.toLowerCase())
    return matchFilter && matchSearch
  })

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-[1000px] mx-auto px-4 sm:px-6 py-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-[22px] sm:text-[26px] font-semibold text-[var(--text-primary)] tracking-tight">Библиотека</h1>
          <div className="flex items-center gap-1 bg-[var(--bg-elevated)] rounded-[var(--radius-md)] p-0.5">
            <button onClick={() => setViewMode('grid')} className={`p-1.5 rounded-[var(--radius-sm)] transition-colors ${viewMode === 'grid' ? 'bg-white shadow-sm text-[var(--text-primary)]' : 'text-[var(--text-tertiary)]'}`}><LayoutGrid size={16} /></button>
            <button onClick={() => setViewMode('list')} className={`p-1.5 rounded-[var(--radius-sm)] transition-colors ${viewMode === 'list' ? 'bg-white shadow-sm text-[var(--text-primary)]' : 'text-[var(--text-tertiary)]'}`}><List size={16} /></button>
          </div>
        </div>

        {/* Search */}
        <div className="relative mb-4">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-tertiary)]" />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Поиск по библиотеке..."
            className="w-full h-10 pl-9 pr-4 bg-[var(--bg-secondary)] border border-[var(--border-subtle)] rounded-[var(--radius-lg)] text-[14px] text-[var(--text-primary)] placeholder:text-[var(--text-tertiary)] outline-none focus:border-[var(--accent-teal)] focus:ring-2 focus:ring-[var(--accent-teal)]/10 transition-all"
          />
        </div>

        {/* Filters */}
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
              {f}
            </button>
          ))}
        </div>

        {/* Content */}
        {viewMode === 'grid' ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {filtered.map(item => (
              <div key={item.id} className="group p-4 rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] hover:border-[var(--border-hover)] hover:shadow-[var(--shadow-md)] transition-all cursor-pointer">
                <div className="flex items-start gap-3">
                  <item.icon size={20} className={`${item.color} flex-shrink-0 mt-0.5`} strokeWidth={1.8} />
                  <div className="min-w-0">
                    <h3 className="text-[14px] font-medium text-[var(--text-primary)] truncate group-hover:text-[var(--accent-teal)] transition-colors">{item.title}</h3>
                    <p className="text-[12px] text-[var(--text-tertiary)] mt-1">{item.type} · {item.client} · {item.date}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="space-y-1">
            {filtered.map(item => (
              <div key={item.id} className="group flex items-center gap-3 px-4 py-3 rounded-[var(--radius-md)] hover:bg-[var(--bg-hover)] transition-colors cursor-pointer">
                <item.icon size={18} className={`${item.color} flex-shrink-0`} strokeWidth={1.8} />
                <div className="flex-1 min-w-0">
                  <h3 className="text-[14px] text-[var(--text-primary)] truncate group-hover:text-[var(--accent-teal)] transition-colors">{item.title}</h3>
                </div>
                <span className="text-[12px] text-[var(--text-tertiary)] hidden sm:block w-24 text-right flex-shrink-0">{item.type}</span>
                <span className="text-[12px] text-[var(--text-tertiary)] hidden md:block w-32 text-right flex-shrink-0">{item.client}</span>
                <span className="text-[12px] text-[var(--text-tertiary)] w-20 text-right flex-shrink-0">{item.date}</span>
              </div>
            ))}
          </div>
        )}

        {filtered.length === 0 && (
          <div className="text-center py-16">
            <p className="text-[14px] text-[var(--text-tertiary)]">Ничего не найдено</p>
          </div>
        )}
      </div>
    </div>
  )
}
