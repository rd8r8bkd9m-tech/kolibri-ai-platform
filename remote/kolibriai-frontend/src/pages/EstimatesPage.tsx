import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  ArrowLeft,
  Calculator,
  Check,
  Copy,
  Download,
  FileDown,
  FileText,
  MoreHorizontal,
  Plus,
  RefreshCw,
  Save,
  Search,
  Sparkles,
  Trash2,
  X,
} from 'lucide-react'
import { useSearchParams } from 'react-router'
import { ai, estimates, health, type Estimate, type Position, type Section } from '@/lib/api'
import { formatDate, formatNum } from '@/lib/utils'

const statusLabels: Record<string, { text: string; className: string }> = {
  draft: { text: 'Черновик', className: 'bg-slate-100 text-slate-600' },
  ready: { text: 'Готова', className: 'bg-cyan-50 text-cyan-700' },
  approved: { text: 'Утверждена', className: 'bg-emerald-50 text-emerald-700' },
  archived: { text: 'В архиве', className: 'bg-zinc-100 text-zinc-500' },
}

const statusOptions = [
  { value: 'draft', label: 'Черновик' },
  { value: 'ready', label: 'Готова' },
  { value: 'approved', label: 'Утверждена' },
  { value: 'archived', label: 'В архиве' },
] as const

const money = (value: string | number | undefined) => `${formatNum(String(value || 0))} ₽`
const numberValue = (value: string | number | undefined) => Number(String(value || '0').replace(',', '.')) || 0
const newSection = (): Section => ({ id: `sec_${Date.now()}`, title: 'Новый раздел', subtotal: '0', positions: [] })
const newPosition = (): Position => ({
  id: `pos_${Date.now()}`,
  code: '',
  name: '',
  unit: 'шт',
  quantity: '1',
  price: '0',
  sum: '0',
  source: '',
  comment: '',
})

type SaveState = 'idle' | 'saving' | 'saved' | 'error'

export default function EstimatesPage() {
  const [view, setView] = useState<'list' | 'editor'>('list')
  const [list, setList] = useState<Estimate[]>([])
  const [current, setCurrent] = useState<Estimate | null>(null)
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [searchParams] = useSearchParams()
  const [apiState, setApiState] = useState<'checking' | 'online' | 'offline'>('checking')
  const [saveState, setSaveState] = useState<SaveState>('idle')
  const [menuOpen, setMenuOpen] = useState(false)
  const [aiResult, setAiResult] = useState<string | null>(null)
  const [aiLoading, setAiLoading] = useState(false)

  const totals = useMemo(() => {
    if (!current) return { positions: 0, sections: 0, localSubtotal: 0 }
    return {
      positions: current.sections.reduce((sum, section) => sum + section.positions.length, 0),
      sections: current.sections.length,
      localSubtotal: current.sections.reduce(
        (sum, section) => sum + section.positions.reduce((lineSum, pos) => lineSum + numberValue(pos.quantity) * numberValue(pos.price), 0),
        0,
      ),
    }
  }, [current])

  const pingBackend = useCallback(async () => {
    try {
      await health.v1()
      setApiState('online')
    } catch {
      try {
        await estimates.list({ page_size: 1 })
        setApiState('online')
      } catch {
        setApiState('offline')
      }
    }
  }, [])

  const loadList = useCallback(async () => {
    setLoading(true)
    try {
      const data = await estimates.list({ search: search || undefined, page_size: 50 })
      setList(data.items)
      setApiState('online')
    } catch (error) {
      console.error('Failed to load estimates', error)
      setApiState('offline')
    } finally {
      setLoading(false)
    }
  }, [search])

  useEffect(() => { pingBackend() }, [pingBackend])
  useEffect(() => { loadList() }, [loadList])
  useEffect(() => {
    const editId = searchParams.get('edit')
    if (editId) void openEditor(editId)
  }, [searchParams])

  const openEditor = async (id: string) => {
    try {
      const estimate = await estimates.get(id)
      setCurrent(estimate)
      setView('editor')
      setSaveState('idle')
      setAiResult(null)
      setApiState('online')
    } catch (error) {
      console.error('Failed to load estimate', error)
      setApiState('offline')
    }
  }

  const serialize = (estimate: Estimate) => ({
    title: estimate.title,
    status: estimate.status,
    client: estimate.client,
    object_name: estimate.object_name,
    region: estimate.region,
    currency: estimate.currency,
    overhead_rate: estimate.overhead_rate,
    vat_rate: estimate.vat_rate,
    sections: estimate.sections.map(section => ({
      title: section.title,
      positions: section.positions.map(pos => ({
        code: pos.code,
        name: pos.name,
        unit: pos.unit,
        quantity: pos.quantity,
        price: pos.price,
        source: pos.source,
        comment: pos.comment,
      })),
    })),
  })

  const handleSave = async () => {
    if (!current) return
    setSaveState('saving')
    try {
      const updated = await estimates.update(current.id, serialize(current))
      setCurrent(updated)
      setSaveState('saved')
      setApiState('online')
      await loadList()
      window.setTimeout(() => setSaveState('idle'), 1800)
    } catch (error) {
      console.error('Failed to save estimate', error)
      setSaveState('error')
      setApiState('offline')
    }
  }

  const handleCalculate = async () => {
    if (!current) return
    setSaveState('saving')
    try {
      const saved = await estimates.update(current.id, serialize(current))
      const calculated = await estimates.calculate(saved.id)
      setCurrent(calculated)
      setSaveState('saved')
      setApiState('online')
      await loadList()
      window.setTimeout(() => setSaveState('idle'), 1800)
    } catch (error) {
      console.error('Failed to calculate estimate', error)
      setSaveState('error')
      setApiState('offline')
    }
  }

  const handleNewEstimate = async () => {
    try {
      const created = await estimates.create({
        title: 'Новая профессиональная смета',
        client: 'Новый клиент',
        object_name: 'Объект',
        region: 'Москва',
        overhead_rate: '7',
        vat_rate: '20',
        sections: [{ title: 'Работы и материалы', positions: [] }],
      })
      await openEditor(created.id)
      await loadList()
    } catch (error) {
      console.error('Failed to create estimate', error)
      setApiState('offline')
    }
  }

  const updateCurrent = (patch: Partial<Estimate>) => {
    if (!current) return
    setCurrent({ ...current, ...patch })
    setSaveState('idle')
  }

  const updateSection = (sectionId: string, patch: Partial<Section>) => {
    if (!current) return
    updateCurrent({ sections: current.sections.map(section => section.id === sectionId ? { ...section, ...patch } : section) })
  }

  const updatePosition = (sectionId: string, positionId: string, patch: Partial<Position>) => {
    if (!current) return
    updateCurrent({
      sections: current.sections.map(section => section.id !== sectionId ? section : {
        ...section,
        positions: section.positions.map(pos => pos.id === positionId ? { ...pos, ...patch } : pos),
      }),
    })
  }

  const addSection = () => current && updateCurrent({ sections: [...current.sections, newSection()] })
  const removeSection = (sectionId: string) => current && updateCurrent({ sections: current.sections.filter(section => section.id !== sectionId) })
  const addPosition = (sectionId: string) => {
    if (!current) return
    updateCurrent({
      sections: current.sections.map(section => section.id === sectionId ? { ...section, positions: [...section.positions, newPosition()] } : section),
    })
  }
  const removePosition = (sectionId: string, positionId: string) => {
    if (!current) return
    updateCurrent({
      sections: current.sections.map(section => section.id === sectionId ? { ...section, positions: section.positions.filter(pos => pos.id !== positionId) } : section),
    })
  }

  const handleDuplicate = async () => {
    if (!current) return
    const duplicate = await estimates.duplicate(current.id)
    setMenuOpen(false)
    await openEditor(duplicate.id)
    await loadList()
  }

  const handleDelete = async () => {
    if (!current || !window.confirm('Удалить смету?')) return
    await estimates.delete(current.id)
    setMenuOpen(false)
    setCurrent(null)
    setView('list')
    await loadList()
  }

  const handleAiAnalyze = async () => {
    if (!current) return
    setAiLoading(true)
    setAiResult(null)
    try {
      const saved = await estimates.update(current.id, serialize(current))
      setCurrent(saved)
      const result = await ai.analyzeEstimate(saved.id)
      setAiResult(result.content)
      setApiState('online')
    } catch {
      setAiResult('Backend недоступен или анализ временно не выполнен.')
      setApiState('offline')
    } finally {
      setAiLoading(false)
    }
  }

  if (view === 'editor' && current) {
    return (
      <div className="min-h-full bg-[var(--bg-primary)]">
        <div className="mx-auto flex w-full max-w-[1280px] flex-col gap-4 px-3 pb-[calc(env(safe-area-inset-bottom)+1rem)] pt-3 sm:px-6 sm:py-5">
          <div className="flex flex-col gap-3 border-b border-[var(--border-subtle)] pb-4 lg:flex-row lg:items-center">
            <div className="flex min-w-0 items-start gap-2">
              <button onClick={() => { setView('list'); setCurrent(null); void loadList() }} className="mt-1 flex h-10 w-10 shrink-0 items-center justify-center rounded-[var(--radius-md)] border border-[var(--border-subtle)] hover:bg-[var(--bg-hover)] sm:h-9 sm:w-9" aria-label="Назад">
                <ArrowLeft size={18} />
              </button>
              <div className="min-w-0 flex-1">
                <textarea value={current.title} onChange={event => updateCurrent({ title: event.target.value })} rows={2} className="min-h-[58px] w-full resize-none bg-transparent text-[20px] font-semibold leading-tight tracking-tight text-[var(--text-primary)] outline-none sm:min-h-[64px] sm:text-[24px]" />
                <div className="mt-2 flex flex-wrap items-center gap-2 text-[12px] text-[var(--text-tertiary)]">
                  <span className={`rounded-[var(--radius-pill)] px-2 py-1 font-medium ${statusLabels[current.status]?.className}`}>{statusLabels[current.status]?.text}</span>
                  <span className="max-w-full truncate">{current.id}</span>
                  <span>версия {current.version}</span>
                  <span>{formatDate(current.updated_at)}</span>
                  <span className={apiState === 'online' ? 'text-emerald-600' : apiState === 'offline' ? 'text-red-600' : 'text-[var(--text-tertiary)]'}>
                    API: {apiState === 'online' ? 'подключен' : apiState === 'offline' ? 'нет связи' : 'проверка'}
                  </span>
                </div>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap sm:items-center lg:ml-auto lg:justify-end">
              <select value={current.status} onChange={event => updateCurrent({ status: event.target.value as Estimate['status'] })} className="col-span-2 h-11 min-w-0 rounded-[var(--radius-md)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] px-3 text-[13px] outline-none sm:col-span-1 sm:h-9">
                {statusOptions.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
              <button onClick={handleAiAnalyze} disabled={aiLoading} className="flex h-11 min-w-0 items-center justify-center gap-2 rounded-[var(--radius-md)] border border-violet-200 px-3 text-[13px] font-medium text-violet-700 hover:bg-violet-50 disabled:opacity-50 sm:h-9">
                <Sparkles size={15} className="shrink-0" /> <span className="truncate">{aiLoading ? 'Анализ' : 'AI аудит'}</span>
              </button>
              <button onClick={handleCalculate} disabled={saveState === 'saving'} className="flex h-11 min-w-0 items-center justify-center gap-2 rounded-[var(--radius-md)] border border-[var(--border-subtle)] px-3 text-[13px] font-medium hover:bg-[var(--bg-hover)] disabled:opacity-50 sm:h-9">
                <Calculator size={15} className="shrink-0" /> <span className="truncate">Пересчитать</span>
              </button>
              <button onClick={handleSave} disabled={saveState === 'saving'} className="flex h-11 min-w-0 items-center justify-center gap-2 rounded-[var(--radius-md)] bg-[var(--accent-teal)] px-3 text-[13px] font-medium text-white hover:bg-[var(--accent-teal-hover)] disabled:opacity-50 sm:h-9">
                {saveState === 'saved' ? <Check size={15} className="shrink-0" /> : <Save size={15} className="shrink-0" />} <span className="truncate">{saveState === 'saving' ? 'Сохранение' : saveState === 'saved' ? 'Сохранено' : 'Сохранить'}</span>
              </button>
              <div className="relative">
                <button onClick={() => setMenuOpen(!menuOpen)} className="flex h-11 w-full items-center justify-center rounded-[var(--radius-md)] border border-[var(--border-subtle)] hover:bg-[var(--bg-hover)] sm:h-9 sm:w-9" aria-label="Еще">
                  <MoreHorizontal size={16} />
                </button>
                {menuOpen && (
                  <div className="absolute right-0 top-10 z-20 w-52 rounded-[var(--radius-md)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] py-1 shadow-[var(--shadow-lg)]">
                    <button onClick={handleDuplicate} className="flex w-full items-center gap-2 px-3 py-2 text-left text-[13px] hover:bg-[var(--bg-hover)]"><Copy size={14} /> Дублировать</button>
                    <a href={estimates.pdfUrl(current.id)} target="_blank" rel="noreferrer" className="flex w-full items-center gap-2 px-3 py-2 text-left text-[13px] hover:bg-[var(--bg-hover)]"><Download size={14} /> PDF</a>
                    <a href={estimates.exportUrl(current.id, 'csv')} target="_blank" rel="noreferrer" className="flex w-full items-center gap-2 px-3 py-2 text-left text-[13px] hover:bg-[var(--bg-hover)]"><FileDown size={14} /> CSV</a>
                    <button onClick={handleDelete} className="flex w-full items-center gap-2 px-3 py-2 text-left text-[13px] text-red-600 hover:bg-red-50"><Trash2 size={14} /> Удалить</button>
                  </div>
                )}
              </div>
            </div>
          </div>

          {saveState === 'error' && <div className="rounded-[var(--radius-md)] border border-red-200 bg-red-50 px-3 py-2 text-[13px] text-red-700">Не удалось сохранить. Проверьте соединение с backend API.</div>}
          {aiResult && <div className="rounded-[var(--radius-md)] border border-violet-200 bg-violet-50 px-4 py-3 text-[13px] leading-6 text-violet-900">{aiResult}</div>}

          <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_340px]">
            <main className="flex min-w-0 flex-col gap-4">
              <section className="grid gap-3 rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-3 sm:grid-cols-2 lg:grid-cols-4">
                <label className="text-[12px] font-medium text-[var(--text-tertiary)]">Клиент<input value={current.client || ''} onChange={event => updateCurrent({ client: event.target.value })} className="mt-1 h-11 w-full rounded-[var(--radius-md)] border border-[var(--border-subtle)] bg-[var(--bg-input)] px-3 text-[14px] text-[var(--text-primary)] outline-none focus:border-[var(--accent-teal)] sm:h-10" /></label>
                <label className="text-[12px] font-medium text-[var(--text-tertiary)]">Объект<input value={current.object_name || ''} onChange={event => updateCurrent({ object_name: event.target.value })} className="mt-1 h-11 w-full rounded-[var(--radius-md)] border border-[var(--border-subtle)] bg-[var(--bg-input)] px-3 text-[14px] text-[var(--text-primary)] outline-none focus:border-[var(--accent-teal)] sm:h-10" /></label>
                <label className="text-[12px] font-medium text-[var(--text-tertiary)]">Регион<input value={current.region || ''} onChange={event => updateCurrent({ region: event.target.value })} className="mt-1 h-11 w-full rounded-[var(--radius-md)] border border-[var(--border-subtle)] bg-[var(--bg-input)] px-3 text-[14px] text-[var(--text-primary)] outline-none focus:border-[var(--accent-teal)] sm:h-10" /></label>
                <div className="grid grid-cols-2 gap-2">
                  <label className="text-[12px] font-medium text-[var(--text-tertiary)]">Накл., %<input inputMode="decimal" value={current.overhead_rate} onChange={event => updateCurrent({ overhead_rate: event.target.value })} className="mt-1 h-11 w-full rounded-[var(--radius-md)] border border-[var(--border-subtle)] bg-[var(--bg-input)] px-3 text-[14px] text-[var(--text-primary)] outline-none focus:border-[var(--accent-teal)] sm:h-10" /></label>
                  <label className="text-[12px] font-medium text-[var(--text-tertiary)]">НДС, %<input inputMode="decimal" value={current.vat_rate} onChange={event => updateCurrent({ vat_rate: event.target.value })} className="mt-1 h-11 w-full rounded-[var(--radius-md)] border border-[var(--border-subtle)] bg-[var(--bg-input)] px-3 text-[14px] text-[var(--text-primary)] outline-none focus:border-[var(--accent-teal)] sm:h-10" /></label>
                </div>
              </section>

              {current.sections.map(section => (
                <section key={section.id} className="rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)]">
                  <div className="flex flex-col gap-2 border-b border-[var(--border-subtle)] p-3 sm:flex-row sm:items-center">
                    <input value={section.title} onChange={event => updateSection(section.id, { title: event.target.value })} className="min-w-0 flex-1 bg-transparent text-[16px] font-semibold text-[var(--text-primary)] outline-none" />
                    <div className="flex items-center justify-between gap-2 sm:justify-end">
                      <span className="text-[13px] font-semibold text-[var(--text-secondary)]">{money(section.positions.reduce((sum, pos) => sum + numberValue(pos.quantity) * numberValue(pos.price), 0))}</span>
                      <button onClick={() => removeSection(section.id)} className="flex h-8 w-8 items-center justify-center rounded-[var(--radius-md)] text-[var(--text-tertiary)] hover:bg-red-50 hover:text-red-600" aria-label="Удалить раздел"><Trash2 size={15} /></button>
                    </div>
                  </div>

                  <div className="hidden grid-cols-[84px_minmax(220px,1fr)_70px_96px_118px_124px_40px] gap-2 border-b border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 text-[11px] uppercase tracking-wide text-[var(--text-tertiary)] lg:grid">
                    <span>Код</span><span>Позиция</span><span>Ед.</span><span className="text-right">Кол-во</span><span className="text-right">Цена</span><span className="text-right">Сумма</span><span />
                  </div>

                  <div className="divide-y divide-[var(--border-subtle)]">
                    {section.positions.map(position => {
                      const lineTotal = numberValue(position.quantity) * numberValue(position.price)
                      return (
                        <div key={position.id} className="grid gap-2 p-3 lg:grid-cols-[84px_minmax(220px,1fr)_70px_96px_118px_124px_40px] lg:items-center">
                          <input value={position.code} onChange={event => updatePosition(section.id, position.id, { code: event.target.value })} placeholder="Код" className="h-11 rounded-[var(--radius-md)] border border-[var(--border-subtle)] bg-[var(--bg-input)] px-2 text-[13px] outline-none focus:border-[var(--accent-teal)] lg:h-9" />
                          <div className="grid gap-2">
                            <input value={position.name} onChange={event => updatePosition(section.id, position.id, { name: event.target.value })} placeholder="Название позиции" className="h-11 rounded-[var(--radius-md)] border border-[var(--border-subtle)] bg-[var(--bg-input)] px-2 text-[13px] outline-none focus:border-[var(--accent-teal)] lg:h-9" />
                            <input value={position.source || ''} onChange={event => updatePosition(section.id, position.id, { source: event.target.value })} placeholder="Источник цены" className="h-8 rounded-[var(--radius-md)] border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-2 text-[12px] text-[var(--text-secondary)] outline-none focus:border-[var(--accent-teal)] lg:hidden" />
                          </div>
                          <div className="grid grid-cols-3 gap-2 lg:contents">
                            <input value={position.unit} onChange={event => updatePosition(section.id, position.id, { unit: event.target.value })} placeholder="Ед." className="h-11 rounded-[var(--radius-md)] border border-[var(--border-subtle)] bg-[var(--bg-input)] px-2 text-[13px] outline-none focus:border-[var(--accent-teal)] lg:h-9" />
                            <input inputMode="decimal" value={position.quantity} onChange={event => updatePosition(section.id, position.id, { quantity: event.target.value })} className="h-11 rounded-[var(--radius-md)] border border-[var(--border-subtle)] bg-[var(--bg-input)] px-2 text-right text-[13px] outline-none focus:border-[var(--accent-teal)] lg:h-9" />
                            <input inputMode="decimal" value={position.price} onChange={event => updatePosition(section.id, position.id, { price: event.target.value })} className="h-11 rounded-[var(--radius-md)] border border-[var(--border-subtle)] bg-[var(--bg-input)] px-2 text-right text-[13px] outline-none focus:border-[var(--accent-teal)] lg:h-9" />
                          </div>
                          <div className="flex items-center justify-between gap-2 lg:justify-end">
                            <span className="text-[12px] text-[var(--text-tertiary)] lg:hidden">Сумма</span>
                            <strong className="text-[14px] text-[var(--text-primary)]">{money(lineTotal)}</strong>
                          </div>
                          <button onClick={() => removePosition(section.id, position.id)} className="flex h-11 w-full items-center justify-center rounded-[var(--radius-md)] text-red-600 hover:bg-red-50 lg:h-9 lg:w-9" aria-label="Удалить позицию"><X size={15} /></button>
                        </div>
                      )
                    })}
                  </div>

                  <button onClick={() => addPosition(section.id)} className="flex w-full items-center justify-center gap-2 p-3 text-[13px] font-medium text-[var(--accent-teal)] hover:bg-[var(--bg-hover)]">
                    <Plus size={15} /> Добавить позицию
                  </button>
                </section>
              ))}

              <button onClick={addSection} className="flex h-12 items-center justify-center gap-2 rounded-[var(--radius-lg)] border border-dashed border-[var(--border-hover)] text-[13px] font-medium text-[var(--text-secondary)] hover:border-[var(--accent-teal)] hover:text-[var(--accent-teal)]">
                <Plus size={16} /> Добавить раздел
              </button>
            </main>

            <aside className="xl:sticky xl:top-4 xl:self-start">
              <div className="rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-4 shadow-[var(--shadow-sm)]">
                <div className="mb-4 flex items-center justify-between gap-3">
                  <div>
                    <p className="text-[12px] font-medium uppercase tracking-wide text-[var(--text-tertiary)]">Сводка</p>
                    <h2 className="text-[22px] font-semibold text-[var(--text-primary)]">{money(current.total || totals.localSubtotal)}</h2>
                  </div>
                  <RefreshCw size={20} className={saveState === 'saving' ? 'animate-spin text-[var(--accent-teal)]' : 'text-[var(--text-tertiary)]'} />
                </div>
                <div className="space-y-2 text-[14px]">
                  <SummaryLine label="Разделов" value={String(totals.sections)} />
                  <SummaryLine label="Позиций" value={String(totals.positions)} />
                  <SummaryLine label="Локальный подытог" value={money(totals.localSubtotal)} />
                  <SummaryLine label="Backend подытог" value={money(current.subtotal)} />
                  <SummaryLine label="Накладные" value={money(current.overhead_amount)} />
                  <SummaryLine label="НДС" value={money(current.vat_amount)} />
                </div>
                <div className="mt-4 rounded-[var(--radius-md)] bg-[var(--bg-secondary)] p-3 text-[12px] leading-5 text-[var(--text-secondary)]">
                  Итоги фиксируются backend API при сохранении или пересчете. Локальный подытог помогает сверить несохраненные изменения.
                </div>
              </div>
            </aside>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-full bg-[var(--bg-primary)]">
      <div className="mx-auto max-w-[1120px] px-3 pb-[calc(env(safe-area-inset-bottom)+1.25rem)] pt-5 sm:px-6">
        <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-[26px] font-semibold tracking-tight text-[var(--text-primary)]">Сметы</h1>
            <p className="mt-1 text-[13px] text-[var(--text-tertiary)]">Профессиональный редактор с расчетом через backend API.</p>
          </div>
          <div className="flex items-center gap-2">
            <span className={`inline-flex shrink-0 rounded-[var(--radius-pill)] px-2.5 py-1 text-[12px] font-medium ${apiState === 'online' ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-700'}`}>
              API {apiState === 'online' ? 'online' : apiState === 'checking' ? 'check' : 'offline'}
            </span>
            <button onClick={handleNewEstimate} className="flex h-11 items-center gap-2 rounded-[var(--radius-md)] bg-[var(--accent-teal)] px-3 text-[13px] font-medium text-white hover:bg-[var(--accent-teal-hover)] sm:h-10">
              <Plus size={16} /> Новая смета
            </button>
          </div>
        </div>

        <div className="mb-4 flex items-center gap-2 rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] px-3 py-2">
          <Search size={16} className="text-[var(--text-tertiary)]" />
          <input value={search} onChange={event => setSearch(event.target.value)} placeholder="Поиск по клиенту, объекту или названию" className="h-8 min-w-0 flex-1 bg-transparent text-[14px] outline-none" />
        </div>

        {loading ? (
          <div className="py-20 text-center text-[14px] text-[var(--text-tertiary)]">Загрузка смет...</div>
        ) : list.length === 0 ? (
          <div className="rounded-[var(--radius-lg)] border border-dashed border-[var(--border-hover)] py-20 text-center">
            <FileText size={42} className="mx-auto mb-3 text-[var(--text-tertiary)]" strokeWidth={1.4} />
            <p className="text-[14px] text-[var(--text-secondary)]">{search ? 'Ничего не найдено' : 'Смет пока нет'}</p>
          </div>
        ) : (
          <div className="grid gap-3">
            {list.map(estimate => (
              <button key={estimate.id} onClick={() => openEditor(estimate.id)} className="grid gap-3 rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-4 text-left transition-all hover:border-[var(--border-hover)] hover:shadow-[var(--shadow-sm)] sm:grid-cols-[minmax(0,1fr)_180px] sm:items-center">
                <div className="min-w-0">
                  <div className="mb-1 flex flex-wrap items-center gap-2">
                    <h3 className="min-w-0 truncate text-[15px] font-semibold text-[var(--text-primary)]">{estimate.title}</h3>
                    <span className={`rounded-[var(--radius-pill)] px-2 py-0.5 text-[11px] font-medium ${statusLabels[estimate.status]?.className || ''}`}>{statusLabels[estimate.status]?.text}</span>
                  </div>
                  <p className="truncate text-[12px] text-[var(--text-tertiary)]">{estimate.client || 'Клиент не указан'} · {estimate.object_name || 'Объект не указан'} · {formatDate(estimate.updated_at)}</p>
                </div>
                <div className="flex items-center justify-between gap-3 sm:justify-end">
                  <span className="text-[12px] text-[var(--text-tertiary)] sm:hidden">Итого</span>
                  <strong className="text-[17px] text-[var(--text-primary)]">{money(estimate.total)}</strong>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function SummaryLine({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-[var(--border-subtle)] py-2 last:border-0">
      <span className="text-[var(--text-secondary)]">{label}</span>
      <strong className="text-right font-semibold text-[var(--text-primary)]">{value}</strong>
    </div>
  )
}
