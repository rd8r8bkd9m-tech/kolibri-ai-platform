import { useState, useEffect, useCallback } from 'react'
import { Plus, Search, FileText, ArrowLeft, Download, Sparkles, MoreHorizontal, Copy, FileDown, Trash2, ChevronDown, X, Check } from 'lucide-react'
import { useSearchParams } from 'react-router'
import { estimates, ai, type Estimate, type Position } from '@/lib/api'
import { formatDate, formatNum } from '@/lib/utils'

const statusLabels: Record<string, { text: string; className: string }> = {
  draft: { text: 'Черновик', className: 'bg-gray-100 text-gray-600' },
  ready: { text: 'Готова', className: 'bg-[#e8f8f7] text-[#3ABAB4]' },
  approved: { text: 'Утверждена', className: 'bg-[#e8f0e8] text-[#10b981]' },
  archived: { text: 'В архиве', className: 'bg-gray-100 text-gray-400' },
}

const statusOptions = [
  { value: 'draft', label: 'Черновик' },
  { value: 'ready', label: 'Готова' },
  { value: 'approved', label: 'Утверждена' },
  { value: 'archived', label: 'В архиве' },
]

export default function EstimatesPage() {
  const [view, setView] = useState<'list' | 'editor'>('list')
  const [list, setList] = useState<Estimate[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [current, setCurrent] = useState<Estimate | null>(null)
  const [editingCell, setEditingCell] = useState<{ secId: string; posId: string; field: string } | null>(null)
  const [searchParams] = useSearchParams()
  const [aiResult, setAiResult] = useState<string | null>(null)
  const [aiLoading, setAiLoading] = useState(false)
  const [aiFixLoading, setAiFixLoading] = useState(false)
  const [aiFixChanges, setAiFixChanges] = useState<{ type: string; position: string; old: string; new: string; reason: string }[] | null>(null)
  const [menuOpen, setMenuOpen] = useState(false)
  const [statusMenuOpen, setStatusMenuOpen] = useState(false)
  const [addingPos, setAddingPos] = useState<string | null>(null)
  const [newPos, setNewPos] = useState({ code: '', name: '', unit: 'шт', quantity: '1', price: '0' })

  const loadList = useCallback(async () => {
    setLoading(true)
    try {
      const data = await estimates.list({ search: search || undefined, page_size: 50 })
      setList(data.items)
    } catch (e) { console.error('Failed to load estimates', e) }
    finally { setLoading(false) }
  }, [search])

  useEffect(() => { loadList() }, [loadList])

  useEffect(() => {
    const editId = searchParams.get('edit')
    if (editId) openEditor(editId)
  }, [searchParams])

  const openEditor = async (id: string) => {
    try {
      const est = await estimates.get(id)
      setCurrent(est)
      setView('editor')
      setAiResult(null)
      setAiFixChanges(null)
    } catch (e) { console.error('Failed to load estimate', e) }
  }

  const handleSave = async () => {
    if (!current) return
    try {
      const updated = await estimates.update(current.id, {
        title: current.title,
        status: current.status,
        client: current.client,
        object_name: current.object_name,
        region: current.region,
        vat_rate: current.vat_rate,
        sections: current.sections.map(s => ({
          title: s.title,
          positions: s.positions.map(p => ({
            code: p.code, name: p.name, unit: p.unit,
            quantity: p.quantity, price: p.price,
            source: p.source, comment: p.comment,
          })),
        })),
      })
      setCurrent(updated)
    } catch (e) { console.error('Failed to save', e) }
  }

  const handleAiAnalyze = async () => {
    if (!current) return
    setAiLoading(true)
    setAiResult(null)
    setAiFixChanges(null)
    try {
      const res = await ai.analyzeEstimate(current.id)
      setAiResult(res.content)
    } catch { setAiResult('Ошибка при анализе сметы') }
    finally { setAiLoading(false) }
  }

  const handleAiFix = async () => {
    if (!current) return
    setAiFixLoading(true)
    setAiFixChanges(null)
    try {
      const res = await ai.fixEstimate(current.id)
      if (res.estimate) setCurrent(res.estimate)
      if (res.changes) setAiFixChanges(res.changes)
      setAiResult(null)
    } catch { setAiResult('Ошибка при исправлении сметы') }
    finally { setAiFixLoading(false) }
  }

  const handleDownloadPdf = () => {
    if (!current) return
    window.open(estimates.pdfUrl(current.id), '_blank')
  }

  const handleDuplicate = async () => {
    if (!current) return
    try {
      const dup = await estimates.duplicate(current.id)
      setMenuOpen(false)
      await openEditor(dup.id)
      loadList()
    } catch (e) { console.error('Failed to duplicate', e) }
  }

  const handleExport = (fmt: 'csv' | 'json') => {
    if (!current) return
    window.open(estimates.exportUrl(current.id, fmt), '_blank')
    setMenuOpen(false)
  }

  const handleDelete = async () => {
    if (!current) return
    if (!window.confirm('Удалить смету? Это действие необратимо.')) return
    try {
      await estimates.delete(current.id)
      setMenuOpen(false)
      setView('list')
      setCurrent(null)
      loadList()
    } catch (e) { console.error('Failed to delete', e) }
  }

  const handleNewEstimate = async () => {
    try {
      const created = await estimates.create({
        title: 'Новая смета',
        sections: [{ title: 'Раздел 1', positions: [] }],
      })
      await openEditor(created.id)
      loadList()
    } catch (e) { console.error('Failed to create', e) }
  }

  const updateField = (field: string, value: string | number) => {
    if (!current) return
    setCurrent({ ...current, [field]: value })
  }

  const updatePosition = (secId: string, posId: string, field: string, value: string) => {
    if (!current) return
    setCurrent({
      ...current,
      sections: current.sections.map(s => s.id !== secId ? s : {
        ...s,
        positions: s.positions.map(p => p.id !== posId ? p : { ...p, [field]: value }),
      }),
    })
    setEditingCell(null)
  }

  const updateSectionTitle = (secId: string, title: string) => {
    if (!current) return
    setCurrent({
      ...current,
      sections: current.sections.map(s => s.id !== secId ? s : { ...s, title }),
    })
  }

  const deletePosition = (secId: string, posId: string) => {
    if (!current) return
    if (!window.confirm('Удалить позицию?')) return
    setCurrent({
      ...current,
      sections: current.sections.map(s => s.id !== secId ? s : {
        ...s,
        positions: s.positions.filter(p => p.id !== posId),
      }),
    })
  }

  const deleteSection = (secId: string) => {
    if (!current) return
    if (!window.confirm('Удалить раздел и все позиции?')) return
    setCurrent({
      ...current,
      sections: current.sections.filter(s => s.id !== secId),
    })
  }

  const addSection = () => {
    if (!current) return
    const newId = `sec-${Date.now()}`
    setCurrent({
      ...current,
      sections: [...current.sections, { id: newId, title: 'Новый раздел', subtotal: '0', positions: [] }],
    })
  }

  const startAddPosition = (secId: string) => {
    setAddingPos(secId)
    setNewPos({ code: '', name: '', unit: 'шт', quantity: '1', price: '0' })
  }

  const confirmAddPosition = () => {
    if (!current || !addingPos) return
    if (!newPos.name.trim()) return
    const newId = `pos-${Date.now()}`
    const sum = String(parseFloat(newPos.quantity || '0') * parseFloat(newPos.price || '0'))
    setCurrent({
      ...current,
      sections: current.sections.map(s => s.id !== addingPos ? s : {
        ...s,
        positions: [...s.positions, { id: newId, code: newPos.code, name: newPos.name, unit: newPos.unit, quantity: newPos.quantity, price: newPos.price, sum, source: '', comment: '' }],
      }),
    })
    setAddingPos(null)
  }

  const cancelAddPosition = () => setAddingPos(null)

  const sectionTotal = (positions: Position[]) =>
    positions.reduce((sum, p) => sum + parseFloat(p.quantity || '0') * parseFloat(p.price || '0'), 0)

  // --- EDITOR VIEW ---
  if (view === 'editor' && current) {
    return (
      <div className="h-full overflow-y-auto">
        <div className="max-w-[1100px] mx-auto px-4 sm:px-6 py-4">
          {/* Header */}
          <div className="flex items-center gap-3 mb-4">
            <button onClick={() => { setView('list'); setCurrent(null) }} className="w-8 h-8 flex items-center justify-center rounded-[var(--radius-md)] hover:bg-[var(--bg-hover)] transition-colors">
              <ArrowLeft size={18} />
            </button>

            {editingCell?.field === 'title' ? (
              <input autoFocus defaultValue={current.title} onBlur={e => { updateField('title', e.target.value); setEditingCell(null) }} onKeyDown={e => { if (e.key === 'Enter') { updateField('title', (e.target as HTMLInputElement).value); setEditingCell(null) } }} className="text-[18px] sm:text-[20px] font-semibold text-[var(--text-primary)] bg-transparent border-b-2 border-[var(--accent-teal)] outline-none px-1" />
            ) : (
              <h1 onClick={() => setEditingCell({ secId: '', posId: '', field: 'title' })} className="text-[18px] sm:text-[20px] font-semibold text-[var(--text-primary)] truncate cursor-pointer hover:text-[var(--accent-teal)] transition-colors">{current.title}</h1>
            )}

            {/* Status dropdown */}
            <div className="relative">
              <button onClick={() => setStatusMenuOpen(!statusMenuOpen)} className={`px-2 py-0.5 rounded-[var(--radius-pill)] text-[11px] font-medium flex items-center gap-1 ${statusLabels[current.status]?.className || ''}`}>
                {statusLabels[current.status]?.text}
                <ChevronDown size={10} />
              </button>
              {statusMenuOpen && (
                <>
                  <div className="fixed inset-0 z-40" onClick={() => setStatusMenuOpen(false)} />
                  <div className="absolute left-0 top-8 z-50 bg-[var(--bg-surface)] border border-[var(--border-subtle)] rounded-[var(--radius-lg)] shadow-lg py-1 min-w-[140px]">
                    {statusOptions.map(opt => (
                      <button key={opt.value} onClick={() => { updateField('status', opt.value); setStatusMenuOpen(false) }} className={`w-full text-left px-3 py-1.5 text-[12px] hover:bg-[var(--bg-hover)] transition-colors ${current.status === opt.value ? 'text-[var(--accent-teal)] font-medium' : 'text-[var(--text-primary)]'}`}>
                        {opt.label}
                      </button>
                    ))}
                  </div>
                </>
              )}
            </div>

            <div className="ml-auto flex items-center gap-2">
              <button onClick={handleAiAnalyze} disabled={aiLoading} className="h-8 px-3 rounded-[var(--radius-md)] border border-[var(--accent-lavender)]/30 text-[13px] text-[var(--accent-lavender)] hover:bg-[var(--accent-lavender)]/10 transition-colors flex items-center gap-1.5 disabled:opacity-50">
                <Sparkles size={14} /> {aiLoading ? 'Анализ...' : 'AI анализ'}
              </button>
              <button onClick={handleDownloadPdf} className="h-8 px-3 rounded-[var(--radius-md)] border border-[var(--border-subtle)] text-[13px] text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] transition-colors flex items-center gap-1.5">
                <Download size={14} /> PDF
              </button>
              <div className="relative">
                <button onClick={() => setMenuOpen(!menuOpen)} className="w-8 h-8 flex items-center justify-center rounded-[var(--radius-md)] border border-[var(--border-subtle)] text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] transition-colors">
                  <MoreHorizontal size={16} />
                </button>
                {menuOpen && (
                  <>
                    <div className="fixed inset-0 z-40" onClick={() => setMenuOpen(false)} />
                    <div className="absolute right-0 top-10 z-50 w-52 bg-[var(--bg-surface)] border border-[var(--border-subtle)] rounded-[var(--radius-lg)] shadow-lg py-1">
                      <button onClick={handleDuplicate} className="w-full flex items-center gap-2.5 px-3 py-2 text-[13px] text-[var(--text-primary)] hover:bg-[var(--bg-hover)] transition-colors"><Copy size={14} /> Дублировать</button>
                      <button onClick={() => handleExport('csv')} className="w-full flex items-center gap-2.5 px-3 py-2 text-[13px] text-[var(--text-primary)] hover:bg-[var(--bg-hover)] transition-colors"><FileDown size={14} /> Экспорт CSV</button>
                      <button onClick={() => handleExport('json')} className="w-full flex items-center gap-2.5 px-3 py-2 text-[13px] text-[var(--text-primary)] hover:bg-[var(--bg-hover)] transition-colors"><FileDown size={14} /> Экспорт JSON</button>
                      <div className="border-t border-[var(--border-subtle)] my-1" />
                      <button onClick={handleDelete} className="w-full flex items-center gap-2.5 px-3 py-2 text-[13px] text-red-600 hover:bg-red-50 transition-colors"><Trash2 size={14} /> Удалить</button>
                    </div>
                  </>
                )}
              </div>
              <button onClick={handleSave} className="h-8 px-3 rounded-[var(--radius-md)] bg-[var(--accent-teal)] text-white text-[13px] font-medium hover:bg-[var(--accent-teal-hover)] transition-colors">Сохранить</button>
            </div>
          </div>

          {/* Meta cards */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4 text-[13px]">
            {[
              { key: 'client', label: 'Клиент' },
              { key: 'object_name', label: 'Объект' },
              { key: 'region', label: 'Регион' },
            ].map(({ key, label }) => (
              <div key={key} className="p-3 rounded-[var(--radius-md)] bg-[var(--bg-secondary)]">
                <span className="text-[var(--text-tertiary)]">{label}</span>
                {editingCell?.field === key ? (
                  <input autoFocus defaultValue={(current as never)[key] || ''} onBlur={e => { updateField(key, e.target.value); setEditingCell(null) }} onKeyDown={e => { if (e.key === 'Enter') { updateField(key, (e.target as HTMLInputElement).value); setEditingCell(null) } }} className="w-full text-[14px] font-medium text-[var(--text-primary)] bg-transparent border-b border-[var(--accent-teal)] outline-none mt-1" />
                ) : (
                  <p onClick={() => setEditingCell({ secId: '', posId: '', field: key })} className="text-[var(--text-primary)] font-medium cursor-pointer hover:text-[var(--accent-teal)] transition-colors mt-1">{(current as never)[key] || '—'}</p>
                )}
              </div>
            ))}
            <div className="p-3 rounded-[var(--radius-md)] bg-[var(--bg-secondary)]">
              <span className="text-[var(--text-tertiary)]">Дата</span>
              <p className="text-[var(--text-primary)] font-medium mt-1">{formatDate(current.created_at)}</p>
            </div>
          </div>

          {/* Sections */}
          {current.sections.map(section => (
            <div key={section.id} className="mb-4">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2 flex-1 min-w-0">
                  {editingCell?.secId === section.id && editingCell?.field === 'sectionTitle' ? (
                    <input autoFocus defaultValue={section.title} onBlur={e => { updateSectionTitle(section.id, e.target.value); setEditingCell(null) }} onKeyDown={e => { if (e.key === 'Enter') { updateSectionTitle(section.id, (e.target as HTMLInputElement).value); setEditingCell(null) } }} className="text-[14px] font-semibold text-[var(--text-primary)] bg-transparent border-b-2 border-[var(--accent-teal)] outline-none flex-1" />
                  ) : (
                    <h3 onClick={() => setEditingCell({ secId: section.id, posId: '', field: 'sectionTitle' })} className="text-[14px] font-semibold text-[var(--text-primary)] cursor-pointer hover:text-[var(--accent-teal)] transition-colors truncate">{section.title}</h3>
                  )}
                  <button onClick={() => deleteSection(section.id)} className="w-6 h-6 flex items-center justify-center rounded text-[var(--text-tertiary)] hover:text-red-500 hover:bg-red-50 transition-colors opacity-0 group-hover:opacity-100" style={{ opacity: 1 }}>
                    <Trash2 size={12} />
                  </button>
                </div>
                <span className="text-[13px] font-medium text-[var(--text-secondary)] flex-shrink-0 ml-2">{formatNum(String(sectionTotal(section.positions)))} ₽</span>
              </div>
              <div className="border border-[var(--border-subtle)] rounded-[var(--radius-lg)] overflow-hidden">
                <div className="hidden sm:grid sm:grid-cols-[60px_1fr_60px_80px_100px_100px_32px] gap-2 px-4 py-2 bg-[var(--bg-secondary)] text-[11px] text-[var(--text-tertiary)] uppercase tracking-wider border-b border-[var(--border-subtle)]">
                  <span>Код</span><span>Наименование</span><span>Ед.</span><span className="text-right">Кол-во</span><span className="text-right">Цена</span><span className="text-right">Сумма</span><span></span>
                </div>
                {section.positions.map(pos => {
                  const sum = parseFloat(pos.quantity || '0') * parseFloat(pos.price || '0')
                  return (
                    <div key={pos.id} className="group/row sm:grid sm:grid-cols-[60px_1fr_60px_80px_100px_100px_32px] gap-2 px-4 py-2.5 border-b border-[var(--border-subtle)] last:border-0 items-center hover:bg-[var(--bg-secondary)]/50 transition-colors">
                      {/* Code */}
                      {editingCell?.secId === section.id && editingCell?.posId === pos.id && editingCell?.field === 'code' ? (
                        <input autoFocus defaultValue={pos.code} onBlur={e => { updatePosition(section.id, pos.id, 'code', e.target.value); setEditingCell(null) }} onKeyDown={e => { if (e.key === 'Enter') updatePosition(section.id, pos.id, 'code', (e.target as HTMLInputElement).value) }} className="text-[12px] font-mono text-[var(--text-tertiary)] bg-transparent border-b border-[var(--accent-teal)] outline-none w-full" />
                      ) : (
                        <span onClick={() => setEditingCell({ secId: section.id, posId: pos.id, field: 'code' })} className="text-[12px] text-[var(--text-tertiary)] font-mono cursor-pointer hover:text-[var(--accent-teal)]">{pos.code}</span>
                      )}
                      {/* Name */}
                      {editingCell?.secId === section.id && editingCell?.posId === pos.id && editingCell?.field === 'name' ? (
                        <input autoFocus defaultValue={pos.name} onBlur={e => { updatePosition(section.id, pos.id, 'name', e.target.value); setEditingCell(null) }} onKeyDown={e => { if (e.key === 'Enter') updatePosition(section.id, pos.id, 'name', (e.target as HTMLInputElement).value) }} className="text-[13px] text-[var(--text-primary)] bg-transparent border-b border-[var(--accent-teal)] outline-none w-full" />
                      ) : (
                        <span onClick={() => setEditingCell({ secId: section.id, posId: pos.id, field: 'name' })} className="text-[13px] text-[var(--text-primary)] cursor-pointer hover:text-[var(--accent-teal)] transition-colors">{pos.name}</span>
                      )}
                      {/* Unit */}
                      {editingCell?.secId === section.id && editingCell?.posId === pos.id && editingCell?.field === 'unit' ? (
                        <input autoFocus defaultValue={pos.unit} onBlur={e => { updatePosition(section.id, pos.id, 'unit', e.target.value); setEditingCell(null) }} onKeyDown={e => { if (e.key === 'Enter') updatePosition(section.id, pos.id, 'unit', (e.target as HTMLInputElement).value) }} className="text-[12px] text-[var(--text-secondary)] bg-transparent border-b border-[var(--accent-teal)] outline-none w-full" />
                      ) : (
                        <span onClick={() => setEditingCell({ secId: section.id, posId: pos.id, field: 'unit' })} className="text-[12px] text-[var(--text-secondary)] cursor-pointer hover:text-[var(--accent-teal)]">{pos.unit}</span>
                      )}
                      {/* Quantity */}
                      {editingCell?.secId === section.id && editingCell?.posId === pos.id && editingCell?.field === 'quantity' ? (
                        <input autoFocus type="number" defaultValue={pos.quantity} onBlur={e => updatePosition(section.id, pos.id, 'quantity', e.target.value)} onKeyDown={e => e.key === 'Enter' && updatePosition(section.id, pos.id, 'quantity', (e.target as HTMLInputElement).value)} className="w-16 text-right text-[13px] border border-[var(--accent-teal)] rounded px-1 outline-none" />
                      ) : (
                        <div className="text-right"><button onClick={() => setEditingCell({ secId: section.id, posId: pos.id, field: 'quantity' })} className="text-[13px] text-[var(--text-primary)] hover:text-[var(--accent-teal)] transition-colors">{pos.quantity}</button></div>
                      )}
                      {/* Price */}
                      {editingCell?.secId === section.id && editingCell?.posId === pos.id && editingCell?.field === 'price' ? (
                        <input autoFocus type="number" step="0.01" defaultValue={pos.price} onBlur={e => updatePosition(section.id, pos.id, 'price', e.target.value)} onKeyDown={e => e.key === 'Enter' && updatePosition(section.id, pos.id, 'price', (e.target as HTMLInputElement).value)} className="w-20 text-right text-[13px] border border-[var(--accent-teal)] rounded px-1 outline-none" />
                      ) : (
                        <div className="text-right"><button onClick={() => setEditingCell({ secId: section.id, posId: pos.id, field: 'price' })} className="text-[13px] text-[var(--text-primary)] hover:text-[var(--accent-teal)] transition-colors">{formatNum(pos.price)}</button></div>
                      )}
                      {/* Sum */}
                      <span className="text-[13px] font-medium text-[var(--text-primary)] text-right">{formatNum(String(sum))}</span>
                      {/* Delete */}
                      <button onClick={() => deletePosition(section.id, pos.id)} className="w-6 h-6 flex items-center justify-center rounded text-[var(--text-tertiary)] hover:text-red-500 hover:bg-red-50 transition-colors opacity-0 group-hover/row:opacity-100">
                        <X size={12} />
                      </button>
                    </div>
                  )
                })}

                {/* Add position row */}
                {addingPos === section.id ? (
                  <div className="sm:grid sm:grid-cols-[60px_1fr_60px_80px_100px_100px_32px] gap-2 px-4 py-2.5 bg-[var(--accent-teal)]/5 border-t border-[var(--accent-teal)]/20">
                    <input value={newPos.code} onChange={e => setNewPos({ ...newPos, code: e.target.value })} placeholder="Код" className="text-[12px] font-mono bg-transparent border-b border-[var(--accent-teal)] outline-none px-1" />
                    <input value={newPos.name} onChange={e => setNewPos({ ...newPos, name: e.target.value })} placeholder="Наименование" autoFocus className="text-[13px] bg-transparent border-b border-[var(--accent-teal)] outline-none px-1" />
                    <input value={newPos.unit} onChange={e => setNewPos({ ...newPos, unit: e.target.value })} placeholder="Ед." className="text-[12px] bg-transparent border-b border-[var(--accent-teal)] outline-none px-1" />
                    <input type="number" value={newPos.quantity} onChange={e => setNewPos({ ...newPos, quantity: e.target.value })} className="text-[13px] text-right bg-transparent border-b border-[var(--accent-teal)] outline-none px-1" />
                    <input type="number" step="0.01" value={newPos.price} onChange={e => setNewPos({ ...newPos, price: e.target.value })} className="text-[13px] text-right bg-transparent border-b border-[var(--accent-teal)] outline-none px-1" />
                    <span className="text-[13px] text-right text-[var(--text-tertiary)]">{formatNum(String(parseFloat(newPos.quantity || '0') * parseFloat(newPos.price || '0')))} ₽</span>
                    <div className="flex gap-1">
                      <button onClick={confirmAddPosition} className="w-6 h-6 flex items-center justify-center rounded text-emerald-600 hover:bg-emerald-50"><Check size={14} /></button>
                      <button onClick={cancelAddPosition} className="w-6 h-6 flex items-center justify-center rounded text-red-500 hover:bg-red-50"><X size={14} /></button>
                    </div>
                  </div>
                ) : (
                  <button onClick={() => startAddPosition(section.id)} className="w-full flex items-center gap-2 px-4 py-2 text-[12px] text-[var(--text-tertiary)] hover:text-[var(--accent-teal)] hover:bg-[var(--bg-hover)] transition-colors border-t border-[var(--border-subtle)]">
                    <Plus size={12} /> Добавить позицию
                  </button>
                )}
              </div>
            </div>
          ))}

          {/* Add section button */}
          <button onClick={addSection} className="w-full flex items-center justify-center gap-2 py-3 mb-4 rounded-[var(--radius-lg)] border-2 border-dashed border-[var(--border-subtle)] text-[13px] text-[var(--text-tertiary)] hover:border-[var(--accent-teal)] hover:text-[var(--accent-teal)] transition-colors">
            <Plus size={16} /> Добавить раздел
          </button>

          {/* Totals */}
          <div className="border border-[var(--border-subtle)] rounded-[var(--radius-lg)] p-4 bg-[var(--bg-secondary)]">
            <div className="space-y-2 text-[14px]">
              <div className="flex justify-between"><span className="text-[var(--text-secondary)]">Подытог</span><span className="font-medium">{formatNum(current.subtotal)} ₽</span></div>
              <div className="flex justify-between items-center">
                <span className="text-[var(--text-secondary)]">НДС</span>
                <div className="flex items-center gap-2">
                  {editingCell?.field === 'vat_rate' ? (
                    <input autoFocus type="number" defaultValue={current.vat_rate} onBlur={e => { updateField('vat_rate', parseFloat(e.target.value) || 0); setEditingCell(null) }} onKeyDown={e => { if (e.key === 'Enter') { updateField('vat_rate', parseFloat((e.target as HTMLInputElement).value) || 0); setEditingCell(null) } }} className="w-12 text-right text-[13px] border border-[var(--accent-teal)] rounded px-1 outline-none" />
                  ) : (
                    <span onClick={() => setEditingCell({ secId: '', posId: '', field: 'vat_rate' })} className="text-[13px] font-medium cursor-pointer hover:text-[var(--accent-teal)]">{current.vat_rate}%</span>
                  )}
                  <span className="font-medium">{formatNum(current.vat_amount)} ₽</span>
                </div>
              </div>
              <div className="flex justify-between pt-2 border-t border-[var(--border-subtle)]">
                <span className="font-semibold text-[var(--text-primary)]">ИТОГО</span>
                <span className="font-semibold text-[18px] text-[var(--accent-teal)]">{formatNum(current.total)} ₽</span>
              </div>
            </div>
          </div>

          {/* AI Fix Changes */}
          {aiFixChanges && aiFixChanges.length > 0 && (
            <div className="mt-4 border border-emerald-200 rounded-[var(--radius-lg)] p-4 bg-emerald-50">
              <div className="flex items-center gap-2 mb-3">
                <Check size={14} className="text-emerald-600" />
                <span className="text-[13px] font-medium text-emerald-700">Исправления применены</span>
                <button onClick={() => setAiFixChanges(null)} className="ml-auto text-[11px] text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]">Закрыть</button>
              </div>
              <div className="space-y-1.5">
                {aiFixChanges.map((c, i) => (
                  <div key={i} className="flex items-center gap-2 text-[12px]">
                    <span className="text-emerald-600">✓</span>
                    <span className="text-[var(--text-primary)]">{c.position}:</span>
                    <span className="text-red-500 line-through">{c.old}</span>
                    <span className="text-emerald-600">→ {c.new}</span>
                    <span className="text-[var(--text-tertiary)]">({c.reason})</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* AI Analysis result */}
          {aiResult && (
            <div className="mt-4 border border-[var(--accent-lavender)]/20 rounded-[var(--radius-lg)] p-4 bg-[var(--accent-lavender)]/5">
              <div className="flex items-center gap-2 mb-2">
                <Sparkles size={14} className="text-[var(--accent-lavender)]" />
                <span className="text-[13px] font-medium text-[var(--accent-lavender)]">AI-анализ</span>
                <button onClick={() => setAiResult(null)} className="ml-auto text-[11px] text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]">Закрыть</button>
              </div>
              <p className="text-[13px] text-[var(--text-primary)] leading-relaxed whitespace-pre-wrap mb-3">{aiResult}</p>
              <button onClick={handleAiFix} disabled={aiFixLoading} className="h-8 px-3 rounded-[var(--radius-md)] bg-[var(--accent-lavender)] text-white text-[13px] font-medium hover:bg-[var(--accent-lavender)]/80 transition-colors flex items-center gap-1.5 disabled:opacity-50">
                <Sparkles size={14} /> {aiFixLoading ? 'Исправляю...' : 'Исправить по рекомендациям AI'}
              </button>
            </div>
          )}
        </div>
      </div>
    )
  }

  // --- LIST VIEW ---
  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-[1000px] mx-auto px-4 sm:px-6 py-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-6">
          <h1 className="text-[22px] sm:text-[26px] font-semibold text-[var(--text-primary)] tracking-tight">Сметы</h1>
          <div className="flex items-center gap-2">
            <div className="relative flex-1 sm:flex-none">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-tertiary)]" />
              <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Поиск..." className="h-9 pl-8 pr-3 w-full sm:w-56 bg-[var(--bg-secondary)] border border-[var(--border-subtle)] rounded-[var(--radius-md)] text-[13px] outline-none focus:border-[var(--accent-teal)] transition-colors" />
            </div>
            <button onClick={handleNewEstimate} className="h-9 px-3 bg-[var(--accent-teal)] text-white rounded-[var(--radius-md)] text-[13px] font-medium hover:bg-[var(--accent-teal-hover)] transition-colors flex items-center gap-1.5 flex-shrink-0">
              <Plus size={15} /> <span className="hidden sm:inline">Новая смета</span>
            </button>
          </div>
        </div>

        {loading ? (
          <div className="text-center py-16 text-[var(--text-tertiary)]">Загрузка...</div>
        ) : list.length === 0 ? (
          <div className="text-center py-16">
            <FileText size={40} className="mx-auto text-[var(--text-tertiary)] mb-3" strokeWidth={1.2} />
            <p className="text-[14px] text-[var(--text-tertiary)]">{search ? 'Ничего не найдено' : 'Смет пока нет'}</p>
          </div>
        ) : (
          <div className="space-y-2">
            {list.map(est => (
              <div key={est.id} onClick={() => openEditor(est.id)} className="group flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4 p-4 rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] hover:border-[var(--border-hover)] hover:shadow-[var(--shadow-sm)] transition-all cursor-pointer">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <h3 className="text-[14px] font-medium text-[var(--text-primary)] truncate group-hover:text-[var(--accent-teal)] transition-colors">{est.title}</h3>
                    <span className={`px-2 py-0.5 rounded-[var(--radius-pill)] text-[11px] font-medium flex-shrink-0 ${statusLabels[est.status]?.className || ''}`}>{statusLabels[est.status]?.text}</span>
                  </div>
                  <p className="text-[12px] text-[var(--text-tertiary)]">{est.client || '—'} · {est.object_name || '—'} · {formatDate(est.created_at)}</p>
                </div>
                <div className="flex items-center gap-3 flex-shrink-0">
                  <span className="text-[15px] font-semibold text-[var(--text-primary)]">{formatNum(est.total)} ₽</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
