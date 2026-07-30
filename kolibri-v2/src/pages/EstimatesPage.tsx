import { useState, useEffect, useCallback, useRef } from 'react'
import { Plus, Search, FileText, ArrowLeft, Sparkles, Send, MessageSquareText, BookOpenCheck, Check, Pencil } from 'lucide-react'
import { useLocation, useNavigate, useSearchParams } from 'react-router'
import { estimates, workCatalog, ai, type Estimate, type EstimateTaxRegime, type WorkCatalogItem } from '@/lib/api'
import { formatDate, formatNum } from '@/lib/utils'
import EstimatePositionRow, { type EditingEstimateCell } from '@/features/estimates/EstimatePositionRow'
import EstimateRevisionHistory from '@/features/estimates/EstimateRevisionHistory'
import EstimateEvidencePanel, { EstimateTruthBadge } from '@/features/estimates/EstimateEvidencePanel'
import { estimateEvidenceSummary } from '@/features/estimates/estimateEvidence'
import {
  deleteEstimatePosition,
  estimateTotalsEqual,
  recalculateEstimate,
  updateEstimatePosition,
  updateEstimatePositionName,
  updateEstimateRate,
  type EstimateRateField,
} from '@/features/estimates/estimateMath'
import { downloadEstimateExport, estimateExportFilename } from '@/features/estimates/estimateExport'
import EstimateDocumentFlow from '@/features/estimates/EstimateDocumentFlow'
import EstimateEditorChrome from '@/features/estimates/EstimateEditorChrome'
import EstimateMobileTotalBar from '@/features/estimates/EstimateMobileTotalBar'
import EstimateBasicsEditor from '@/features/estimates/EstimateBasicsEditor'
import EmbeddedPdfViewer from '@/features/documents/EmbeddedPdfViewer'
import EmbeddedWorkbookViewer from '@/features/documents/EmbeddedWorkbookViewer'
import EstimateDecimalInput from '@/features/estimates/EstimateDecimalInput'

export default function EstimatesPage() {
  const location = useLocation()
  const navigate = useNavigate()
  const [view, setView] = useState<'list' | 'editor' | 'catalog'>('list')
  const [list, setList] = useState<Estimate[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [current, setCurrent] = useState<Estimate | null>(null)
  // React state is applied after the current browser event. When an input
  // loses focus because the user immediately clicks Save/Recalculate, the
  // button handler can otherwise observe the previous render and submit the
  // old quantity or price. These refs are the synchronous source of truth for
  // user actions; state remains the rendering source of truth.
  const currentRef = useRef<Estimate | null>(null)
  const dirtyRef = useRef(false)
  const [editingCell, setEditingCell] = useState<EditingEstimateCell | null>(null)
  const [searchParams] = useSearchParams()
  const [aiResult, setAiResult] = useState<string | null>(null)
  const [aiLoading, setAiLoading] = useState(false)
  const [mutation, setMutation] = useState<'saving' | 'calculating' | null>(null)
  const [mutationError, setMutationError] = useState<string | null>(null)
  const [dirty, setDirty] = useState(false)
  const [revisionRefreshToken, setRevisionRefreshToken] = useState(0)
  const [exporting, setExporting] = useState<'pdf' | 'csv' | 'json' | 'xlsx' | null>(null)
  const [pdfPreviewUrl, setPdfPreviewUrl] = useState<string | null>(null)
  const [workbookPreviewVersion, setWorkbookPreviewVersion] = useState<number | null>(null)
  const [estimateCommand, setEstimateCommand] = useState('')
  const [commandLoading, setCommandLoading] = useState(false)
  const [commandMessages, setCommandMessages] = useState<{ role: 'user' | 'assistant'; content: string }[]>([])
  const [catalogItems, setCatalogItems] = useState<WorkCatalogItem[]>([])
  const [catalogLoading, setCatalogLoading] = useState(false)
  const [catalogEditing, setCatalogEditing] = useState<string | null>(null)
  const [catalogPrice, setCatalogPrice] = useState('')
  const [catalogSaving, setCatalogSaving] = useState(false)
  const [catalogError, setCatalogError] = useState('')
  const sourceChatPath = (() => {
    const from = (location.state as { from?: unknown } | null)?.from
    return typeof from === 'string' && /^\/chat(?:\/[A-Za-z0-9._~-]+)?$/.test(from)
      ? from
      : null
  })()

  const closeEditor = () => {
    currentRef.current = null
    dirtyRef.current = false
    setView('list')
    setCurrent(null)
    if (sourceChatPath) navigate(-1)
    else navigate('/estimates', { replace: true })
  }

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
      currentRef.current = est
      dirtyRef.current = false
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
        currentRef.current = est
        dirtyRef.current = false
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
    title: estimate.title,
    client: estimate.client,
    object_name: estimate.object_name,
    region: estimate.region,
    price_as_of: estimate.price_as_of,
    currency: estimate.currency,
    overhead_rate: estimate.overhead_rate,
    profit_rate: estimate.profit_rate || '0',
    contingency_rate: estimate.contingency_rate || '0',
    general_contractor_rate: estimate.general_contractor_rate || '0',
    discount_rate: estimate.discount_rate || '0',
    vat_rate: estimate.vat_rate,
    tax_regime: estimate.tax_regime,
    estimate_status: estimate.estimate_status,
    pricing_status: estimate.pricing_status,
    scope_status: estimate.scope_status,
    price_sources: estimate.price_sources,
    evidence_issues: estimate.evidence_issues,
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
    currentRef.current = updated
    dirtyRef.current = false
    setCurrent(updated)
    setList(items => items.map(item => item.id === updated.id ? updated : item))
    setDirty(false)
    setRevisionRefreshToken(value => value + 1)
    if (!estimateTotalsEqual(updated, recalculated)) {
      setMutationError('Сервер вернул итоги, которые не совпадают с детерминированным расчётом. Экспорт заблокирован до повторной проверки.')
    }
  }

  const handleSave = async () => {
    const draft = currentRef.current
    if (!draft) return
    setMutation('saving')
    setMutationError(null)
    try {
      acceptMutation(await estimates.update(draft.id, updatePayload(draft)))
    } catch (e) {
      console.error('Failed to save', e)
      setMutationError('Не удалось сохранить смету. Обновите данные и повторите попытку.')
    } finally {
      setMutation(null)
    }
  }

  const handleRecalculate = async () => {
    const draft = currentRef.current
    if (!draft) return
    setMutation('calculating')
    setMutationError(null)
    try {
      acceptMutation(dirtyRef.current
        ? await estimates.update(draft.id, updatePayload(draft))
        : await estimates.calculate(draft.id, draft.version))
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

  const handlePreviewPdf = async () => {
    const draft = currentRef.current
    if (!draft) return
    if (dirtyRef.current || !estimateTotalsEqual(draft, recalculateEstimate(draft))) {
      setMutationError('Сначала сохраните согласованные итоги сметы, затем формируйте PDF.')
      return
    }
    setExporting('pdf')
    setMutationError(null)
    try {
      setPdfPreviewUrl(estimates.pdfUrl(draft.id, draft.version))
    } catch (e) {
      console.error('Failed to preview PDF', e)
      setMutationError('Не удалось открыть предпросмотр PDF.')
    } finally {
      setExporting(null)
    }
  }

  const handleDuplicate = async () => {
    if (!current) return
    try {
      const dup = await estimates.duplicate(current.id)
      await openEditor(dup.id)
      loadList()
    } catch (e) { console.error('Failed to duplicate', e) }
  }

  const handleExport = async (fmt: 'csv' | 'json' | 'xlsx') => {
    const draft = currentRef.current
    if (!draft) return
    if (dirtyRef.current || !estimateTotalsEqual(draft, recalculateEstimate(draft))) {
      setMutationError('Сначала сохраните согласованные итоги сметы, затем выполняйте экспорт.')
      return
    }
    setExporting(fmt)
    setMutationError(null)
    try {
      await downloadEstimateExport(
        estimates.exportUrl(draft.id, fmt, draft.version),
        estimateExportFilename(draft.title, draft.version, fmt),
        fmt,
      )
    } catch (e) {
      console.error(`Failed to export ${fmt}`, e)
      setMutationError(`Не удалось скачать ${fmt.toUpperCase()}. Повторите попытку.`)
    } finally {
      setExporting(null)
    }
  }

  const handlePreviewWorkbook = (version: number) => {
    setWorkbookPreviewVersion(version)
  }

  const handleDelete = async () => {
    const draft = currentRef.current
    if (!draft) return
    if (!window.confirm('Удалить смету? Это действие необратимо.')) return
    try {
      await estimates.delete(draft.id)
      setView('list')
      currentRef.current = null
      dirtyRef.current = false
      setCurrent(null)
      loadList()
    } catch (e) { console.error('Failed to delete', e) }
  }

  const handleNewEstimate = async () => {
    try {
      const catalog = await workCatalog.list()
      const starterPositions = catalog.items.slice(0, 6).map((item, index) => ({
        code: `К-${String(index + 1).padStart(3, '0')}`,
        name: item.name,
        unit: item.unit,
        quantity: '1',
        price: item.latest_price,
        source: item.price_source,
        comment: '',
      }))
      const created = await estimates.create({
        title: 'Новая смета',
        client: '',
        object_name: 'Объект без названия',
        region: '',
        source_note: 'Стартовые расценки предварительные и редактируемые. Количества уточняются по проекту.',
        sections: [{
          title: 'Работы по объекту',
          positions: starterPositions.length ? starterPositions : [{
            code: 'К-001',
            name: 'Уточните состав работ',
            unit: 'шт',
            quantity: '1',
            price: '1',
            source: 'Временная позиция до загрузки справочника',
          }],
        }],
      })
      await openEditor(created.id)
      loadList()
    } catch (e) { console.error('Failed to create', e) }
  }

  const updatePosition = (
    secId: string,
    posId: string,
    field: 'quantity' | 'price',
    value: string,
    finalize = true,
  ) => {
    const draft = currentRef.current
    if (!draft) return
    const updated = updateEstimatePosition(draft, secId, posId, field, value)
    if (!updated) {
      if (finalize) setMutationError('Введите неотрицательное число, например 12,5.')
      return
    }
    currentRef.current = updated
    dirtyRef.current = true
    setCurrent(updated)
    setDirty(true)
    setMutationError(null)
    if (finalize) setEditingCell(null)
  }

  const commitPositionName = (secId: string, posId: string, value: string) => {
    const draft = currentRef.current
    if (!draft) return
    const updated = updateEstimatePositionName(draft, secId, posId, value)
    if (!updated) {
      setMutationError('Наименование позиции не может быть пустым.')
      setEditingCell(null)
      return
    }
    currentRef.current = updated
    dirtyRef.current = true
    setCurrent(updated)
    setDirty(true)
    setMutationError(null)
    setEditingCell(null)
  }

  const removePosition = (secId: string, posId: string) => {
    const draft = currentRef.current
    if (!draft) return
    const updated = deleteEstimatePosition(draft, secId, posId)
    currentRef.current = updated
    dirtyRef.current = true
    setCurrent(updated)
    setDirty(true)
    setMutationError(null)
    setEditingCell(null)
  }

  const updateRate = (field: EstimateRateField, value: string) => {
    const draft = currentRef.current
    if (!draft) return
    const updated = updateEstimateRate(draft, field, value)
    if (!updated) {
      setMutationError('Введите ставку от 0 до 999 процентов.')
      return
    }
    currentRef.current = updated
    dirtyRef.current = true
    setCurrent(updated)
    setDirty(true)
    setMutationError(null)
  }

  const updateTaxRegime = (taxRegime: EstimateTaxRegime) => {
    const draft = currentRef.current
    if (!draft) return
    const vatRate: Record<EstimateTaxRegime, string> = {
      unspecified: draft.vat_rate,
      npd: '0',
      usn_exempt: '0',
      usn_vat5: '5',
      usn_vat7: '7',
      osno_vat22: '22',
    }
    const withRate = updateEstimateRate(draft, 'vat_rate', vatRate[taxRegime])
    if (!withRate) return
    const updated = { ...withRate, tax_regime: taxRegime }
    currentRef.current = updated
    dirtyRef.current = true
    setCurrent(updated)
    setDirty(true)
    setMutationError(null)
  }

  const updateBasics = (patch: Partial<Pick<Estimate, 'client' | 'object_name' | 'region' | 'price_as_of'>>) => {
    const draft = currentRef.current
    if (!draft) return
    const updated = { ...draft, ...patch }
    currentRef.current = updated
    dirtyRef.current = true
    setCurrent(updated)
    setDirty(true)
    setMutationError(null)
  }

  const handleEstimateCommand = async () => {
    const command = estimateCommand.trim()
    let draft = currentRef.current
    if (!draft || !command || commandLoading) return
    setEstimateCommand('')
    setCommandMessages(messages => [...messages, { role: 'user', content: command }])
    setCommandLoading(true)
    setMutationError(null)
    try {
      if (dirtyRef.current) {
        draft = await estimates.update(draft.id, updatePayload(draft))
        acceptMutation(draft)
      }
      const result = await estimates.command(draft.id, draft.version, command)
      acceptMutation(result.estimate)
      setCommandMessages(messages => [...messages, { role: 'assistant', content: result.message }])
    } catch (error) {
      console.error('Failed to apply estimate command', error)
      setCommandMessages(messages => [...messages, {
        role: 'assistant',
        content: 'Не удалось безопасно применить правку. Укажите уникальную позицию или ставку в процентах.',
      }])
    } finally {
      setCommandLoading(false)
    }
  }

  const handleApprove = async () => {
    const draft = currentRef.current
    if (!draft || mutation !== null) return
    setMutation('saving')
    setMutationError(null)
    try {
      acceptMutation(await estimates.update(draft.id, { ...updatePayload(draft), status: 'approved' }))
    } catch (error) {
      console.error('Failed to approve estimate', error)
      setMutationError('Не удалось утвердить смету и обновить справочник работ.')
    } finally {
      setMutation(null)
    }
  }

  const openCatalog = async () => {
    setView('catalog')
    setCatalogLoading(true)
    try {
      setCatalogItems((await workCatalog.list(search)).items)
    } catch (error) {
      console.error('Failed to load work catalog', error)
      setCatalogItems([])
    } finally {
      setCatalogLoading(false)
    }
  }

  const saveCatalogPrice = async (item: WorkCatalogItem) => {
    if (catalogSaving || !catalogPrice.trim()) return
    setCatalogSaving(true)
    setCatalogError('')
    try {
      const updated = await workCatalog.updatePrice(item.id, catalogPrice)
      setCatalogItems(items => items.map(currentItem => currentItem.id === updated.id ? updated : currentItem))
      setCatalogEditing(null)
    } catch (error) {
      console.error('Failed to update work catalog price', error)
      setCatalogError('Не удалось сохранить цену. Введите неотрицательное число.')
    } finally {
      setCatalogSaving(false)
    }
  }

  // --- EDITOR VIEW ---
  if (view === 'editor' && current) {
    const evidence = estimateEvidenceSummary(current)
    const evidenceByPosition = new Map(evidence.rows.map(row => [row.position.id, row]))
    const canExport = !dirty && estimateTotalsEqual(current, recalculateEstimate(current))
    return (
      <div className="estimate-editor-page h-full overflow-y-auto">
        <div className="estimate-editor-shell max-w-[1100px] mx-auto px-4 sm:px-6 py-4">
          <EstimateEditorChrome
            title={current.title}
            backLabel={sourceChatPath ? 'Вернуться в чат' : 'К списку смет'}
            truthStatus={evidence.estimateStatus}
            canExport={canExport}
            exporting={exporting}
            aiLoading={aiLoading}
            mutation={mutation}
            approved={current.status === 'approved'}
            dirty={dirty}
            onBack={closeEditor}
            onAiAnalyze={() => void handleAiAnalyze()}
            onPreviewPdf={() => void handlePreviewPdf()}
            onPreviewWorkbook={() => handlePreviewWorkbook(current.version)}
            onRecalculate={() => void handleRecalculate()}
            onApprove={() => void handleApprove()}
            onDuplicate={() => void handleDuplicate()}
            onExport={format => void handleExport(format)}
            onDelete={() => void handleDelete()}
            onSave={() => void handleSave()}
          />

          {mutationError && (
            <div className="mb-4 rounded-[var(--radius-md)] border border-red-200 bg-red-50 px-3 py-2 text-[13px] text-red-700" role="alert">
              {mutationError}
            </div>
          )}

          <EstimateBasicsEditor estimate={current} dirty={dirty} onChange={updateBasics} />

          <EstimateDocumentFlow key={current.id} estimate={current} canGenerate={canExport} />

          <EstimateEvidencePanel estimate={current} collapsible />

          {current.sections.map(section => (
            <section key={section.id} className="estimate-section mb-4">
              <div className="estimate-section-header flex items-center justify-between mb-2">
                <h3 className="text-[14px] font-semibold text-[var(--text-primary)]">{section.title}</h3>
                <span className="text-[13px] font-medium text-[var(--text-secondary)]">{formatNum(section.subtotal)} ₽</span>
              </div>
              <div className="estimate-positions">
                <div className="estimate-position-head">
                  <span>Код</span><span>Наименование</span><span>Ед.</span><span className="text-right">Кол-во</span><span className="text-right">Цена</span><span className="text-right">Сумма</span><span aria-hidden="true" />
                </div>
                {section.positions.map(pos => (
                  <EstimatePositionRow
                    key={pos.id}
                    sectionId={section.id}
                    position={pos}
                    editingCell={editingCell}
                    evidence={evidenceByPosition.get(pos.id)}
                    onEdit={field => setEditingCell({ secId: section.id, posId: pos.id, field })}
                    onDraft={(field, value) => updatePosition(section.id, pos.id, field, value, false)}
                    onCommit={(field, value) => updatePosition(section.id, pos.id, field, value)}
                    onNameCommit={value => commitPositionName(section.id, pos.id, value)}
                    onDelete={() => removePosition(section.id, pos.id)}
                  />
                ))}
              </div>
            </section>
          ))}

          <div className="estimate-summary border border-[var(--border-subtle)] rounded-[var(--radius-lg)] p-4 bg-[var(--bg-secondary)]">
            <div className="space-y-2 text-[14px]">
              <div className="estimate-tax-regime-row">
                <label htmlFor="estimate-tax-regime">Налоговый режим</label>
                <select id="estimate-tax-regime" value={current.tax_regime || 'unspecified'} onChange={event => updateTaxRegime(event.target.value as EstimateTaxRegime)}>
                  <option value="unspecified">Не выбран</option>
                  <option value="npd">Самозанятый · НПД · без НДС</option>
                  <option value="usn_exempt">УСН · освобождение от НДС</option>
                  <option value="usn_vat5">УСН · НДС 5%</option>
                  <option value="usn_vat7">УСН · НДС 7%</option>
                  <option value="osno_vat22">ОСНО · НДС 22%</option>
                </select>
              </div>
              <div className="flex justify-between"><span className="text-[var(--text-secondary)]">Подытог</span><span className="font-medium">{formatNum(current.subtotal)} ₽</span></div>
              <div className="estimate-rate-row">
                <label htmlFor="estimate-overhead-rate">Накладные расходы</label>
                <div><EstimateDecimalInput id="estimate-overhead-rate" inputMode="decimal" value={current.overhead_rate} onDraft={value => updateRate('overhead_rate', value)} onCommit={value => updateRate('overhead_rate', value)} onInvalidDraft={value => updateRate('overhead_rate', value)} aria-label="Ставка накладных расходов, процентов" /><span>%</span><strong>{formatNum(current.overhead_amount)} ₽</strong></div>
              </div>
              <div className="estimate-rate-row">
                <label htmlFor="estimate-profit-rate">Сметная прибыль</label>
                <div><EstimateDecimalInput id="estimate-profit-rate" inputMode="decimal" value={current.profit_rate || '0'} onDraft={value => updateRate('profit_rate', value)} onCommit={value => updateRate('profit_rate', value)} onInvalidDraft={value => updateRate('profit_rate', value)} aria-label="Ставка сметной прибыли, процентов" /><span>%</span><strong>{formatNum(current.profit_amount || '0')} ₽</strong></div>
              </div>
              <div className="estimate-rate-row">
                <label htmlFor="estimate-contingency-rate">Резерв на непредвиденные расходы</label>
                <div><EstimateDecimalInput id="estimate-contingency-rate" inputMode="decimal" value={current.contingency_rate || '0'} onDraft={value => updateRate('contingency_rate', value)} onCommit={value => updateRate('contingency_rate', value)} onInvalidDraft={value => updateRate('contingency_rate', value)} aria-label="Ставка резерва, процентов" /><span>%</span><strong>{formatNum(current.contingency_amount || '0')} ₽</strong></div>
              </div>
              <div className="estimate-rate-row">
                <label htmlFor="estimate-general-contractor-rate">Генподрядные услуги</label>
                <div><EstimateDecimalInput id="estimate-general-contractor-rate" inputMode="decimal" value={current.general_contractor_rate || '0'} onDraft={value => updateRate('general_contractor_rate', value)} onCommit={value => updateRate('general_contractor_rate', value)} onInvalidDraft={value => updateRate('general_contractor_rate', value)} aria-label="Ставка генподрядных услуг, процентов" /><span>%</span><strong>{formatNum(current.general_contractor_amount || '0')} ₽</strong></div>
              </div>
              <div className="estimate-rate-row">
                <label htmlFor="estimate-discount-rate">Скидка</label>
                <div><EstimateDecimalInput id="estimate-discount-rate" inputMode="decimal" value={current.discount_rate || '0'} onDraft={value => updateRate('discount_rate', value)} onCommit={value => updateRate('discount_rate', value)} onInvalidDraft={value => updateRate('discount_rate', value)} aria-label="Ставка скидки, процентов" /><span>%</span><strong>− {formatNum(current.discount_amount || '0')} ₽</strong></div>
              </div>
              <div className="estimate-rate-row">
                <label htmlFor="estimate-vat-rate">НДС</label>
                <div><EstimateDecimalInput id="estimate-vat-rate" inputMode="decimal" value={current.vat_rate} onDraft={value => updateRate('vat_rate', value)} onCommit={value => updateRate('vat_rate', value)} onInvalidDraft={value => updateRate('vat_rate', value)} aria-label="Ставка НДС, процентов" /><span>%</span><strong>{formatNum(current.vat_amount)} ₽</strong></div>
              </div>
              <div className="flex justify-between pt-2 border-t border-[var(--border-subtle)]">
                <span className="font-semibold text-[var(--text-primary)]">ИТОГО</span>
                <span className="font-semibold text-[18px] text-[var(--accent-teal)]">{formatNum(current.total)} ₽</span>
              </div>
            </div>
          </div>

          <section className="estimate-command-panel" aria-labelledby="estimate-command-title">
            <div className="estimate-command-heading">
              <MessageSquareText size={16} />
              <div>
                <h2 id="estimate-command-title">Правки в диалоге</h2>
                <p>Например: «накладные 12%, прибыль 8%, НДС 22%» или «удали позицию Доставка».</p>
              </div>
            </div>
            {commandMessages.length > 0 && (
              <div className="estimate-command-messages" aria-live="polite">
                {commandMessages.map((message, index) => (
                  <div key={`${message.role}-${index}`} className={`estimate-command-message is-${message.role}`}>
                    {message.content}
                  </div>
                ))}
                {commandLoading && <div className="estimate-command-message is-assistant">Применяю и пересчитываю…</div>}
              </div>
            )}
            <form className="estimate-command-composer" onSubmit={event => { event.preventDefault(); void handleEstimateCommand() }}>
              <input
                value={estimateCommand}
                onChange={event => setEstimateCommand(event.target.value)}
                placeholder="Что изменить в смете?"
                aria-label="Команда для изменения сметы"
                disabled={commandLoading}
              />
              <button type="submit" disabled={commandLoading || !estimateCommand.trim()} aria-label="Применить правку">
                <Send size={16} />
              </button>
            </form>
          </section>

          <EstimateRevisionHistory
            estimateId={current.id}
            currentVersion={current.version}
            refreshToken={revisionRefreshToken}
            onPreviewPdf={version => setPdfPreviewUrl(estimates.pdfUrl(current.id, version))}
            onPreviewWorkbook={handlePreviewWorkbook}
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
        <EstimateMobileTotalBar
          total={current.total}
          dirty={dirty}
          saving={mutation === 'saving'}
          disabled={mutation !== null || !dirty}
          onSave={() => void handleSave()}
        />
        {pdfPreviewUrl && <EmbeddedPdfViewer url={pdfPreviewUrl} title={current.title} onClose={() => setPdfPreviewUrl(null)} />}
        {workbookPreviewVersion !== null && (
          <EmbeddedWorkbookViewer
            title={`${current.title} · версия ${workbookPreviewVersion}`}
            downloadUrl={estimates.exportUrl(current.id, 'xlsx', workbookPreviewVersion)}
            loadKey={`${current.id}:${workbookPreviewVersion}`}
            load={() => estimates.workbook(current.id, workbookPreviewVersion)}
            onClose={() => setWorkbookPreviewVersion(null)}
          />
        )}
      </div>
    )
  }

  if (view === 'catalog') {
    return (
      <div className="h-full overflow-y-auto">
        <div className="max-w-[1000px] mx-auto px-4 sm:px-6 py-6">
          <header className="flex items-center gap-3 mb-6">
            <button aria-label="К сметам" onClick={() => setView('list')} className="estimate-editor-icon-button rounded-[var(--radius-md)] hover:bg-[var(--bg-hover)] transition-colors"><ArrowLeft size={18} /></button>
            <div>
              <h1 className="text-[22px] font-semibold text-[var(--text-primary)]">Справочник работ</h1>
              <p className="text-[13px] text-[var(--text-tertiary)]">Пополняется только из утверждённых смет вашей компании.</p>
            </div>
          </header>
          {catalogLoading ? <div className="py-14 text-center text-[var(--text-tertiary)]">Загрузка…</div> : (
            <div className="work-catalog-list">
              {catalogError && <p className="work-catalog-error" role="alert">{catalogError}</p>}
              <div className="work-catalog-head"><span>Работа</span><span>Раздел</span><span>Ед.</span><span>Текущая цена</span><span>Источник</span></div>
              {catalogItems.map(item => (
                <div className="work-catalog-row" key={item.id}>
                  <strong>{item.name}</strong><span>{item.category || '—'}</span><span>{item.unit}</span>
                  {catalogEditing === item.id ? <form className="work-catalog-price-editor" onSubmit={event => { event.preventDefault(); void saveCatalogPrice(item) }}><input autoFocus inputMode="decimal" value={catalogPrice} onChange={event => setCatalogPrice(event.target.value)} aria-label={`Текущая цена: ${item.name}`} /><button type="submit" disabled={catalogSaving}><Check size={15} /></button><button type="button" onClick={() => setCatalogEditing(null)}>×</button></form> : <button type="button" className={`work-catalog-price ${Number(item.latest_price) === 0 ? 'needs-price' : ''}`} onClick={() => { setCatalogEditing(item.id); setCatalogPrice(item.latest_price) }}><span>{Number(item.latest_price) === 0 ? 'Заполнить цену' : `${formatNum(item.latest_price)} ₽`}</span><Pencil size={13} /></button>}
                  <span className="work-catalog-source">{item.price_source === 'estimate' || !item.price_source ? `Смета · ${item.usage_count} исп.` : item.price_source}{item.price_observed_at ? <small>{formatDate(item.price_observed_at)}</small> : null}</span>
                </div>
              ))}
              {catalogItems.length === 0 && <div className="py-14 text-center text-[var(--text-tertiary)]">Утвердите первую смету — её позиции появятся здесь.</div>}
            </div>
          )}
        </div>
      </div>
    )
  }

  // --- LIST VIEW ---
  return (
    <div className="estimate-list-page h-full overflow-y-auto">
      <div className="estimate-list-shell max-w-[1000px] mx-auto px-4 sm:px-6 py-6">
        <div className="estimate-list-header flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-6">
          <h1 className="text-[22px] sm:text-[26px] font-semibold text-[var(--text-primary)] tracking-tight">Сметы</h1>
          <div className="flex items-center gap-2">
            <button aria-label="Открыть справочник работ" onClick={() => void openCatalog()} className="estimate-list-catalog h-9 px-3 border border-[var(--border-subtle)] text-[var(--text-secondary)] rounded-[var(--radius-md)] text-[13px] font-medium hover:bg-[var(--bg-hover)] transition-colors flex items-center gap-1.5">
              <BookOpenCheck size={15} /> <span className="hidden sm:inline">Справочник</span>
            </button>
            <div className="estimate-list-search relative flex-1 sm:flex-none">
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
            <button aria-label="Создать новую смету" onClick={handleNewEstimate} className="estimate-list-new h-9 px-3 bg-[var(--accent-teal)] text-white rounded-[var(--radius-md)] text-[13px] font-medium hover:bg-[var(--accent-teal-hover)] transition-colors flex items-center gap-1.5 flex-shrink-0">
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
          <div className="estimate-list-items space-y-2">
            {list.map(est => (
              <button type="button" key={est.id} onClick={() => openEditor(est.id)} className="estimate-list-item group flex w-full flex-col sm:flex-row sm:items-center gap-2 sm:gap-4 p-4 rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] hover:border-[var(--border-hover)] hover:shadow-[var(--shadow-sm)] transition-all cursor-pointer text-left">
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
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
