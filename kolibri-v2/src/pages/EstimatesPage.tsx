import { useState, useEffect, useCallback } from 'react'
import { Plus, Search, FileText, ArrowLeft, Download, Sparkles, MoreHorizontal, Copy, FileDown, Trash2, Calculator, FileSpreadsheet } from 'lucide-react'
import { useSearchParams } from 'react-router'
import { estimates, ai, type Estimate } from '@/lib/api'
import { formatDate, formatNum } from '@/lib/utils'
import EstimatePositionRow, { type EditingEstimateCell } from '@/features/estimates/EstimatePositionRow'
import EstimateRevisionHistory from '@/features/estimates/EstimateRevisionHistory'
import EstimateEvidencePanel, { EstimateTruthBadge } from '@/features/estimates/EstimateEvidencePanel'
import { estimateEvidenceSummary } from '@/features/estimates/estimateEvidence'
import { estimateTotalsEqual, recalculateEstimate, updateEstimatePosition } from '@/features/estimates/estimateMath'

export default function EstimatesPage() {
  const [view, setView] = useState<'list' | 'editor'>('list')
  const [list, setList] = useState<Estimate[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [current, setCurrent] = useState<Estimate | null>(null)
  const [editingCell, setEditingCell] = useState<EditingEstimateCell | null>(null)
  const [searchParams] = useSearchParams()
  const [aiResult, setAiResult] = useState<string | null>(null)
  const [aiLoading, setAiLoading] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const [mutation, setMutation] = useState<'saving' | 'calculating' | null>(null)
  const [mutationError, setMutationError] = useState<string | null>(null)
  const [dirty, setDirty] = useState(false)
  const [revisionRefreshToken, setRevisionRefreshToken] = useState(0)

  const fetchList = useCallback(() => {
    return estimates.list({ search: search || undefined, page_size: 50 })
  }, [search])

  const loadList = useCallback(async () => {
    setLoading(true)
    try {
      const data = await fetchList()
      setList(data.items)
    } catch (e) { console.error('Failed to load estimates', e) }
    finally { setLoading(false) }
  }, [fetchList])

  useEffect(() => {
    let active = true
    void fetchList()
      .then(data => { if (active) setList(data.items) })
      .catch(e => { if (active) console.error('Failed to load estimates', e) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [fetchList])

  const fetchEstimate = useCallback((id: string) => estimates.get(id), [])

  const openEditor = useCallback(async (id: string) => {
    try {
      const est = await fetchEstimate(id)
      setCurrent(est)
      setDirty(false)
      setMutationError(null)
      setView('editor')
    } catch (e) { console.error('Failed to load estimate', e) }
  }, [fetchEstimate])

  const editId = searchParams.get('edit')
  useEffect(() => {
    if (!editId) return
    let active = true
    void fetchEstimate(editId)
      .then(est => {
        if (!active) return
        setCurrent(est)
        setDirty(false)
        setMutationError(null)
        setView('editor')
      })
      .catch(e => { if (active) console.error('Failed to load estimate', e) })
    return () => { active = false }
  }, [editId, fetchEstimate])

  const updatePayload = (estimate: Estimate) => ({
    version: estimate.version,
    overhead_rate: estimate.overhead_rate,
    vat_rate: estimate.vat_rate,
    estimate_status: estimate.estimate_status,
    pricing_status: estimate.pricing_status,
    scope_status: estimate.scope_status,
    price_sources: estimate.price_sources,
    evidence_issues: estimate.evidence_issues,
    price_as_of: estimate.price_as_of,
    assumptions: estimate.assumptions,
    questions: estimate.questions,
    source_note: estimate.source_note,
    sections: estimate.sections.map(s => ({
      title: s.title,
      positions: s.positions.map(p => ({
        code: p.code, name: p.name, unit: p.unit,
        quantity: p.quantity, price: p.price,
        source: p.source,
        source_evidence: p.source_evidence,
        price_evidence: p.price_evidence,
        comment: p.comment,
      })),
    })),
  })

  const acceptMutation = (updated: Estimate) => {
    const recalculated = recalculateEstimate(updated)
    setCurrent(updated)
    setList(items => items.map(item => item.id === updated.id ? updated : item))
    setDirty(false)
    setRevisionRefreshToken(value => value + 1)
    if (!estimateTotalsEqual(updated, recalculated)) {
      setMutationError('Сервер вернул итоги, которые не совпадают с детерминированным расчётом. Экспорт заблокирован до повторной проверки.')
    }
  }

  const handleSave = async () => {
    if (!current) return
    setMutation('saving')
    setMutationError(null)
    try {
      acceptMutation(await estimates.update(current.id, updatePayload(current)))
    } catch (e) {
      console.error('Failed to save', e)
      setMutationError('Не удалось сохранить смету. Обновите данные и повторите попытку.')
    } finally {
      setMutation(null)
    }
  }

  const handleRecalculate = async () => {
    if (!current) return
    setMutation('calculating')
    setMutationError(null)
    try {
      acceptMutation(dirty
        ? await estimates.update(current.id, updatePayload(current))
        : await estimates.calculate(current.id, current.version))
    } catch (e) {
      console.error('Failed to recalculate', e)
      setMutationError('Не удалось пересчитать смету. Обновите данные и повторите попытку.')
    } finally {
      setMutation(null)
    }
  }

  const handleAiAnalyze = async () => {
    if (!current) return
    setAiLoading(true)
    setAiResult(null)
    try {
      const res = await ai.analyzeEstimate(current.id)
      setAiResult(res.content)
    } catch { setAiResult('Ошибка при анализе сметы') }
    finally { setAiLoading(false) }
  }

  const handleDownloadPdf = () => {
    if (!current) return
    if (dirty || !estimateTotalsEqual(current, recalculateEstimate(current))) {
      setMutationError('Сначала сохраните согласованные итоги сметы, затем формируйте PDF.')
      return
    }
    window.open(estimates.pdfUrl(current.id, current.version), '_blank', 'noopener,noreferrer')
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

  const handleExport = (fmt: 'csv' | 'json' | 'xlsx') => {
    if (!current) return
    if (dirty || !estimateTotalsEqual(current, recalculateEstimate(current))) {
      setMutationError('Сначала сохраните согласованные итоги сметы, затем выполняйте экспорт.')
      return
    }
    window.open(estimates.exportUrl(current.id, fmt, current.version), '_blank', 'noopener,noreferrer')
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

  const updatePosition = (secId: string, posId: string, field: 'quantity' | 'price', value: string) => {
    if (!current) return
    const updated = updateEstimatePosition(current, secId, posId, field, value)
    if (!updated) {
      setMutationError('Введите неотрицательное число, например 12,5.')
      setEditingCell(null)
      return
    }
    setCurrent(updated)
    setDirty(true)
    setMutationError(null)
    setEditingCell(null)
  }

  // --- EDITOR VIEW ---
  if (view === 'editor' && current) {
    const evidence = estimateEvidenceSummary(current)
    const evidenceByPosition = new Map(evidence.rows.map(row => [row.position.id, row]))
    const canExport = !dirty && estimateTotalsEqual(current, recalculateEstimate(current))
    return (
      <div className="estimate-editor-page h-full overflow-y-auto">
        <div className="estimate-editor-shell max-w-[1100px] mx-auto px-4 sm:px-6 py-4">
          <header className="estimate-editor-header">
            <div className="estimate-editor-identity">
            <button aria-label="К списку смет" onClick={() => { setView('list'); setCurrent(null) }} className="estimate-editor-icon-button rounded-[var(--radius-md)] hover:bg-[var(--bg-hover)] transition-colors">
              <ArrowLeft size={18} />
            </button>
            <h1 className="text-[18px] sm:text-[20px] font-semibold text-[var(--text-primary)] truncate">{current.title}</h1>
            <EstimateTruthBadge status={evidence.estimateStatus} />
            </div>
            <div className="estimate-editor-toolbar" role="toolbar" aria-label="Действия со сметой">
              <button onClick={handleAiAnalyze} disabled={aiLoading} className="estimate-editor-action border border-[var(--accent-lavender)]/30 text-[var(--accent-lavender)] hover:bg-[var(--accent-lavender)]/10 transition-colors flex items-center gap-1.5 disabled:opacity-50">
                <Sparkles size={14} /> {aiLoading ? 'Анализ...' : 'AI анализ'}
              </button>
              <button onClick={handleDownloadPdf} disabled={!canExport} className="estimate-editor-action border border-[var(--border-subtle)] text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] transition-colors flex items-center gap-1.5 disabled:cursor-not-allowed disabled:opacity-50">
                <Download size={14} /> PDF
              </button>
              <button onClick={() => handleExport('xlsx')} disabled={!canExport} className="estimate-editor-action border border-[var(--border-subtle)] text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] transition-colors flex items-center gap-1.5 disabled:cursor-not-allowed disabled:opacity-50">
                <FileSpreadsheet size={14} /> XLSX
              </button>
              <button onClick={() => void handleRecalculate()} disabled={mutation !== null} className="estimate-editor-action border border-[var(--border-subtle)] text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] transition-colors flex items-center gap-1.5 disabled:opacity-50">
                <Calculator size={14} /> {mutation === 'calculating' ? 'Считаю…' : 'Пересчитать'}
              </button>
              <div className="estimate-editor-menu-anchor">
                <button aria-label="Дополнительные действия" aria-expanded={menuOpen} onClick={() => setMenuOpen(!menuOpen)} className="estimate-editor-icon-button rounded-[var(--radius-md)] border border-[var(--border-subtle)] text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] transition-colors">
                  <MoreHorizontal size={16} />
                </button>
                {menuOpen && (
                  <>
                    <div className="fixed inset-0 z-40" onClick={() => setMenuOpen(false)} />
                    <div className="estimate-editor-menu absolute right-0 top-10 z-50 w-52 bg-[var(--bg-surface)] border border-[var(--border-subtle)] rounded-[var(--radius-lg)] shadow-lg py-1">
                      <button onClick={handleDuplicate} className="w-full flex items-center gap-2.5 px-3 py-2 text-[13px] text-[var(--text-primary)] hover:bg-[var(--bg-hover)] transition-colors">
                        <Copy size={14} /> Дублировать
                      </button>
                      <button onClick={() => handleExport('csv')} disabled={!canExport} className="w-full flex items-center gap-2.5 px-3 py-2 text-[13px] text-[var(--text-primary)] hover:bg-[var(--bg-hover)] transition-colors disabled:cursor-not-allowed disabled:opacity-50">
                        <FileDown size={14} /> Экспорт CSV
                      </button>
                      <button onClick={() => handleExport('json')} disabled={!canExport} className="w-full flex items-center gap-2.5 px-3 py-2 text-[13px] text-[var(--text-primary)] hover:bg-[var(--bg-hover)] transition-colors disabled:cursor-not-allowed disabled:opacity-50">
                        <FileDown size={14} /> Экспорт JSON
                      </button>
                      <button onClick={() => handleExport('xlsx')} disabled={!canExport} className="w-full flex items-center gap-2.5 px-3 py-2 text-[13px] text-[var(--text-primary)] hover:bg-[var(--bg-hover)] transition-colors disabled:cursor-not-allowed disabled:opacity-50">
                        <FileSpreadsheet size={14} /> Экспорт XLSX
                      </button>
                      <div className="border-t border-[var(--border-subtle)] my-1" />
                      <button onClick={handleDelete} className="w-full flex items-center gap-2.5 px-3 py-2 text-[13px] text-red-600 hover:bg-red-50 transition-colors">
                        <Trash2 size={14} /> Удалить
                      </button>
                    </div>
                  </>
                )}
              </div>
              <button onClick={() => void handleSave()} disabled={mutation !== null || !dirty} className="estimate-editor-action bg-[var(--accent-teal)] text-white font-medium hover:bg-[var(--accent-teal-hover)] transition-colors disabled:cursor-not-allowed disabled:opacity-50">
                {mutation === 'saving' ? 'Сохраняю…' : dirty ? 'Сохранить' : 'Сохранено'}
              </button>
            </div>
          </header>

          {mutationError && (
            <div className="mb-4 rounded-[var(--radius-md)] border border-red-200 bg-red-50 px-3 py-2 text-[13px] text-red-700" role="alert">
              {mutationError}
            </div>
          )}

          <div className="estimate-meta-grid grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4 text-[13px]">
            <div className="estimate-meta-card p-3 rounded-[var(--radius-md)] bg-[var(--bg-secondary)]">
              <span className="text-[var(--text-tertiary)]">Клиент</span>
              <p className="text-[var(--text-primary)] font-medium">{current.client || '—'}</p>
            </div>
            <div className="estimate-meta-card p-3 rounded-[var(--radius-md)] bg-[var(--bg-secondary)]">
              <span className="text-[var(--text-tertiary)]">Объект</span>
              <p className="text-[var(--text-primary)] font-medium">{current.object_name || '—'}</p>
            </div>
            <div className="estimate-meta-card p-3 rounded-[var(--radius-md)] bg-[var(--bg-secondary)]">
              <span className="text-[var(--text-tertiary)]">Регион</span>
              <p className="text-[var(--text-primary)] font-medium">{current.region || '—'}</p>
            </div>
            <div className="estimate-meta-card p-3 rounded-[var(--radius-md)] bg-[var(--bg-secondary)]">
              <span className="text-[var(--text-tertiary)]">Версия</span>
              <p className="text-[var(--text-primary)] font-medium">{current.version}{dirty ? ' · есть изменения' : ''}</p>
            </div>
          </div>

          <EstimateEvidencePanel estimate={current} />

          {current.sections.map(section => (
            <section key={section.id} className="estimate-section mb-4">
              <div className="estimate-section-header flex items-center justify-between mb-2">
                <h3 className="text-[14px] font-semibold text-[var(--text-primary)]">{section.title}</h3>
                <span className="text-[13px] font-medium text-[var(--text-secondary)]">{formatNum(section.subtotal)} ₽</span>
              </div>
              <div className="estimate-positions">
                <div className="estimate-position-head">
                  <span>Код</span><span>Наименование</span><span>Ед.</span><span className="text-right">Кол-во</span><span className="text-right">Цена</span><span className="text-right">Сумма</span>
                </div>
                {section.positions.map(pos => (
                  <EstimatePositionRow
                    key={pos.id}
                    sectionId={section.id}
                    position={pos}
                    editingCell={editingCell}
                    evidence={evidenceByPosition.get(pos.id)}
                    onEdit={field => setEditingCell({ secId: section.id, posId: pos.id, field })}
                    onCommit={(field, value) => updatePosition(section.id, pos.id, field, value)}
                  />
                ))}
              </div>
            </section>
          ))}

          <div className="estimate-summary border border-[var(--border-subtle)] rounded-[var(--radius-lg)] p-4 bg-[var(--bg-secondary)]">
            <div className="space-y-2 text-[14px]">
              <div className="flex justify-between"><span className="text-[var(--text-secondary)]">Подытог</span><span className="font-medium">{formatNum(current.subtotal)} ₽</span></div>
              <div className="flex justify-between"><span className="text-[var(--text-secondary)]">Накладные ({current.overhead_rate}%)</span><span className="font-medium">{formatNum(current.overhead_amount)} ₽</span></div>
              <div className="flex justify-between"><span className="text-[var(--text-secondary)]">НДС ({current.vat_rate}%)</span><span className="font-medium">{formatNum(current.vat_amount)} ₽</span></div>
              <div className="flex justify-between pt-2 border-t border-[var(--border-subtle)]">
                <span className="font-semibold text-[var(--text-primary)]">ИТОГО</span>
                <span className="font-semibold text-[18px] text-[var(--accent-teal)]">{formatNum(current.total)} ₽</span>
              </div>
            </div>
          </div>

          <EstimateRevisionHistory
            estimateId={current.id}
            currentVersion={current.version}
            refreshToken={revisionRefreshToken}
          />

          {/* AI Analysis result */}
          {aiResult && (
            <div className="estimate-ai-result mt-4 border border-[var(--accent-lavender)]/20 rounded-[var(--radius-lg)] p-4 bg-[var(--accent-lavender)]/5">
              <div className="flex items-center gap-2 mb-2">
                <Sparkles size={14} className="text-[var(--accent-lavender)]" />
                <span className="text-[13px] font-medium text-[var(--accent-lavender)]">AI-анализ</span>
                <button onClick={() => setAiResult(null)} className="ml-auto text-[11px] text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]">Закрыть</button>
              </div>
              <p className="text-[13px] text-[var(--text-primary)] leading-relaxed whitespace-pre-wrap">{aiResult}</p>
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
              <input
                value={search}
                onChange={e => {
                  setLoading(true)
                  setSearch(e.target.value)
                }}
                placeholder="Поиск..."
                className="h-9 pl-8 pr-3 w-full sm:w-56 bg-[var(--bg-secondary)] border border-[var(--border-subtle)] rounded-[var(--radius-md)] text-[13px] outline-none focus:border-[var(--accent-teal)] transition-colors"
              />
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
                    {est.status === 'archived'
                      ? <span className="estimate-truth-badge preliminary">В архиве</span>
                      : <EstimateTruthBadge status={estimateEvidenceSummary(est).estimateStatus} />}
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
