import { useState, useMemo } from 'react'
import { Plus, Search, MoreHorizontal, FileText, ArrowLeft, ChevronDown } from 'lucide-react'

interface Position {
  id: string
  code: string
  name: string
  unit: string
  quantity: number
  price: number
}

interface Section {
  id: string
  title: string
  positions: Position[]
}

const initialSections: Section[] = [
  {
    id: 's1', title: 'Электромонтажные работы',
    positions: [
      { id: 'p1', code: 'ЭМ-01-001', name: 'Прокладка кабеля ВВГнг 3x2.5', unit: 'м', quantity: 150, price: 85.50 },
      { id: 'p2', code: 'ЭМ-01-002', name: 'Монтаж розетки', unit: 'шт', quantity: 25, price: 450.00 },
      { id: 'p3', code: 'ЭМ-01-003', name: 'Установка автомата 16А', unit: 'шт', quantity: 12, price: 320.00 },
      { id: 'p4', code: 'ЭМ-01-004', name: 'Сборка электрощита', unit: 'компл', quantity: 1, price: 8500.00 },
    ],
  },
  {
    id: 's2', title: 'Сантехнические работы',
    positions: [
      { id: 'p5', code: 'СТ-02-001', name: 'Установка смесителя', unit: 'шт', quantity: 4, price: 1200.00 },
      { id: 'p6', code: 'СТ-02-002', name: 'Прокладка трубы ППР 25мм', unit: 'м', quantity: 35, price: 180.00 },
    ],
  },
]

const estimateList = [
  { id: 'e1', title: 'Смета на электромонтаж дома 120 м²', client: 'Иванов И.И.', object: 'д. Примерное', total: '290 027,70 ₽', status: 'ready', date: '25.06.2026' },
  { id: 'e2', title: 'Смета на ремонт офиса 80 м²', client: 'ООО ТехноСервис', object: 'Москва', total: '26 400,00 ₽', status: 'draft', date: '22.06.2026' },
  { id: 'e3', title: 'Смета на монтаж Видеонаблюдения', client: 'ООО Безопасность', object: 'Склад 500 м²', total: '156 800,00 ₽', status: 'approved', date: '18.06.2026' },
  { id: 'e4', title: 'Смета на реконструкцию фасада', client: 'ИП Петров', object: 'СПб', total: '890 450,00 ₽', status: 'draft', date: '10.06.2026' },
]

const statusLabels: Record<string, { text: string; className: string }> = {
  draft: { text: 'Черновик', className: 'bg-gray-100 text-gray-600' },
  ready: { text: 'Готова', className: 'bg-[#e8f8f7] text-[#3ABAB4]' },
  approved: { text: 'Утверждена', className: 'bg-[#e8f0e8] text-[#10b981]' },
}

export default function EstimatesPage() {
  const [view, setView] = useState<'list' | 'editor'>('list')
  const [selectedEstimate, setSelectedEstimate] = useState<string | null>(null)
  const [sections, setSections] = useState<Section[]>(initialSections)
  const [editingCell, setEditingCell] = useState<{ secId: string; posId: string; field: 'quantity' | 'price' } | null>(null)

  const totals = useMemo(() => {
    let subtotal = 0
    sections.forEach(s => s.positions.forEach(p => { subtotal += p.quantity * p.price }))
    const vat = subtotal * 0.20
    const total = subtotal + vat
    return { subtotal, vat, total }
  }, [sections])

  const updatePosition = (secId: string, posId: string, field: 'quantity' | 'price', value: number) => {
    setSections(prev => prev.map(s => s.id !== secId ? s : {
      ...s,
      positions: s.positions.map(p => p.id !== posId ? p : { ...p, [field]: value }),
    }))
    setEditingCell(null)
  }

  const formatNum = (n: number) => n.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  const sectionTotal = (s: Section) => s.positions.reduce((sum, p) => sum + p.quantity * p.price, 0)

  if (view === 'editor' || selectedEstimate) {
    return (
      <div className="h-full overflow-y-auto">
        <div className="max-w-[1100px] mx-auto px-4 sm:px-6 py-4">
          {/* Header */}
          <div className="flex items-center gap-3 mb-4">
            <button onClick={() => { setView('list'); setSelectedEstimate(null) }} className="w-8 h-8 flex items-center justify-center rounded-[var(--radius-md)] hover:bg-[var(--bg-hover)] transition-colors">
              <ArrowLeft size={18} />
            </button>
            <h1 className="text-[18px] sm:text-[20px] font-semibold text-[var(--text-primary)] truncate">Смета на электромонтаж дома 120 м²</h1>
            <span className={`px-2 py-0.5 rounded-[var(--radius-pill)] text-[11px] font-medium ${statusLabels.ready.className}`}>{statusLabels.ready.text}</span>
            <div className="ml-auto flex items-center gap-2">
              <button className="h-8 px-3 rounded-[var(--radius-md)] border border-[var(--border-subtle)] text-[13px] text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] transition-colors flex items-center gap-1.5">
                <FileText size={14} /> PDF
              </button>
              <button className="h-8 px-3 rounded-[var(--radius-md)] bg-[var(--accent-teal)] text-white text-[13px] font-medium hover:bg-[var(--accent-teal-hover)] transition-colors">Сохранить</button>
            </div>
          </div>

          {/* Info row */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4 text-[13px]">
            <div className="p-3 rounded-[var(--radius-md)] bg-[var(--bg-secondary)]">
              <span className="text-[var(--text-tertiary)]">Клиент</span>
              <p className="text-[var(--text-primary)] font-medium">Иванов И.И.</p>
            </div>
            <div className="p-3 rounded-[var(--radius-md)] bg-[var(--bg-secondary)]">
              <span className="text-[var(--text-tertiary)]">Объект</span>
              <p className="text-[var(--text-primary)] font-medium">Дом 120 м²</p>
            </div>
            <div className="p-3 rounded-[var(--radius-md)] bg-[var(--bg-secondary)]">
              <span className="text-[var(--text-tertiary)]">Регион</span>
              <p className="text-[var(--text-primary)] font-medium">Московская обл.</p>
            </div>
            <div className="p-3 rounded-[var(--radius-md)] bg-[var(--bg-secondary)]">
              <span className="text-[var(--text-tertiary)]">Дата</span>
              <p className="text-[var(--text-primary)] font-medium">25.06.2026</p>
            </div>
          </div>

          {/* Sections */}
          {sections.map(section => (
            <div key={section.id} className="mb-4">
              <div className="flex items-center justify-between mb-2">
                <h3 className="text-[14px] font-semibold text-[var(--text-primary)]">{section.title}</h3>
                <span className="text-[13px] font-medium text-[var(--text-secondary)]">{formatNum(sectionTotal(section))} ₽</span>
              </div>
              <div className="border border-[var(--border-subtle)] rounded-[var(--radius-lg)] overflow-hidden">
                {/* Table header */}
                <div className="hidden sm:grid sm:grid-cols-[60px_1fr_60px_80px_100px_100px] gap-2 px-4 py-2 bg-[var(--bg-secondary)] text-[11px] text-[var(--text-tertiary)] uppercase tracking-wider border-b border-[var(--border-subtle)]">
                  <span>Код</span><span>Наименование</span><span>Ед.</span><span className="text-right">Кол-во</span><span className="text-right">Цена</span><span className="text-right">Сумма</span>
                </div>
                {/* Positions */}
                {section.positions.map(pos => {
                  const sum = pos.quantity * pos.price
                  return (
                    <div key={pos.id} className="sm:grid sm:grid-cols-[60px_1fr_60px_80px_100px_100px] gap-2 px-4 py-2.5 border-b border-[var(--border-subtle)] last:border-0 items-center hover:bg-[var(--bg-secondary)]/50 transition-colors">
                      <span className="text-[12px] text-[var(--text-tertiary)] font-mono">{pos.code}</span>
                      <span className="text-[13px] text-[var(--text-primary)]">{pos.name}</span>
                      <span className="text-[12px] text-[var(--text-secondary)]">{pos.unit}</span>
                      <div className="text-right">
                        {editingCell?.secId === section.id && editingCell?.posId === pos.id && editingCell?.field === 'quantity' ? (
                          <input autoFocus type="number" defaultValue={pos.quantity} onBlur={e => updatePosition(section.id, pos.id, 'quantity', Number(e.target.value))} onKeyDown={e => e.key === 'Enter' && updatePosition(section.id, pos.id, 'quantity', Number((e.target as HTMLInputElement).value))} className="w-16 text-right text-[13px] border border-[var(--accent-teal)] rounded px-1 outline-none" />
                        ) : (
                          <button onClick={() => setEditingCell({ secId: section.id, posId: pos.id, field: 'quantity' })} className="text-[13px] text-[var(--text-primary)] hover:text-[var(--accent-teal)] transition-colors">{pos.quantity}</button>
                        )}
                      </div>
                      <div className="text-right">
                        {editingCell?.secId === section.id && editingCell?.posId === pos.id && editingCell?.field === 'price' ? (
                          <input autoFocus type="number" step="0.01" defaultValue={pos.price} onBlur={e => updatePosition(section.id, pos.id, 'price', Number(e.target.value))} onKeyDown={e => e.key === 'Enter' && updatePosition(section.id, pos.id, 'price', Number((e.target as HTMLInputElement).value))} className="w-20 text-right text-[13px] border border-[var(--accent-teal)] rounded px-1 outline-none" />
                        ) : (
                          <button onClick={() => setEditingCell({ secId: section.id, posId: pos.id, field: 'price' })} className="text-[13px] text-[var(--text-primary)] hover:text-[var(--accent-teal)] transition-colors">{formatNum(pos.price)}</button>
                        )}
                      </div>
                      <span className="text-[13px] font-medium text-[var(--text-primary)] text-right">{formatNum(sum)}</span>
                    </div>
                  )
                })}
              </div>
            </div>
          ))}

          {/* Totals */}
          <div className="border border-[var(--border-subtle)] rounded-[var(--radius-lg)] p-4 bg-[var(--bg-secondary)]">
            <div className="space-y-2 text-[14px]">
              <div className="flex justify-between"><span className="text-[var(--text-secondary)]">Подытог</span><span className="font-medium">{formatNum(totals.subtotal)} ₽</span></div>
              <div className="flex justify-between"><span className="text-[var(--text-secondary)]">НДС (20%)</span><span className="font-medium">{formatNum(totals.vat)} ₽</span></div>
              <div className="flex justify-between pt-2 border-t border-[var(--border-subtle)]">
                <span className="font-semibold text-[var(--text-primary)]">ИТОГО</span>
                <span className="font-semibold text-[18px] text-[var(--accent-teal)]">{formatNum(totals.total)} ₽</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-[1000px] mx-auto px-4 sm:px-6 py-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-6">
          <h1 className="text-[22px] sm:text-[26px] font-semibold text-[var(--text-primary)] tracking-tight">Сметы</h1>
          <div className="flex items-center gap-2">
            <div className="relative flex-1 sm:flex-none">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-tertiary)]" />
              <input placeholder="Поиск..." className="h-9 pl-8 pr-3 w-full sm:w-56 bg-[var(--bg-secondary)] border border-[var(--border-subtle)] rounded-[var(--radius-md)] text-[13px] outline-none focus:border-[var(--accent-teal)] transition-colors" />
            </div>
            <button onClick={() => setView('editor')} className="h-9 px-3 bg-[var(--accent-teal)] text-white rounded-[var(--radius-md)] text-[13px] font-medium hover:bg-[var(--accent-teal-hover)] transition-colors flex items-center gap-1.5 flex-shrink-0">
              <Plus size={15} /> <span className="hidden sm:inline">Новая смета</span>
            </button>
          </div>
        </div>

        <div className="space-y-2">
          {estimateList.map(est => (
            <div key={est.id} onClick={() => setSelectedEstimate(est.id)} className="group flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4 p-4 rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] hover:border-[var(--border-hover)] hover:shadow-[var(--shadow-sm)] transition-all cursor-pointer">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <h3 className="text-[14px] font-medium text-[var(--text-primary)] truncate group-hover:text-[var(--accent-teal)] transition-colors">{est.title}</h3>
                  <span className={`px-2 py-0.5 rounded-[var(--radius-pill)] text-[11px] font-medium flex-shrink-0 ${statusLabels[est.status]?.className || ''}`}>{statusLabels[est.status]?.text}</span>
                </div>
                <p className="text-[12px] text-[var(--text-tertiary)]">{est.client} · {est.object} · {est.date}</p>
              </div>
              <div className="flex items-center gap-3 flex-shrink-0">
                <span className="text-[15px] font-semibold text-[var(--text-primary)]">{est.total}</span>
                <button className="w-7 h-7 flex items-center justify-center rounded-[var(--radius-md)] text-[var(--text-tertiary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-secondary)] transition-colors">
                  <MoreHorizontal size={16} />
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
