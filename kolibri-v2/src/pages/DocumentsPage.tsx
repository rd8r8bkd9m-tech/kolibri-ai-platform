import { useState, useEffect, useCallback } from 'react'
import { FileText, Search, Plus, ArrowLeft, Download, FileSpreadsheet, Sparkles, Trash2 } from 'lucide-react'
import { useSearchParams } from 'react-router'
import { documents, templates, ai, type Document as Doc, type Template } from '@/lib/api'
import { formatDate } from '@/lib/utils'
import { sandboxedDocumentHtml } from '@/features/documents/sandboxedDocument'

const statusLabels: Record<string, { text: string; className: string }> = {
  draft: { text: 'Черновик', className: 'bg-gray-100 text-gray-600' },
  review: { text: 'На согласовании', className: 'bg-[#fef3e8] text-[#f59e0b]' },
  final: { text: 'Финал', className: 'bg-[#e8f8f7] text-[#3ABAB4]' },
}

const typeLabels: Record<string, string> = {
  contract: 'Договор', act: 'Акт', letter: 'Письмо', proposal: 'КП', report: 'Отчёт', memo: 'Записка', custom: 'Документ',
}

export default function DocumentsPage() {
  const [view, setView] = useState<'list' | 'editor'>('list')
  const [list, setList] = useState<Doc[]>([])
  const [loading, setLoading] = useState(true)
  const [current, setCurrent] = useState<Doc | null>(null)
  const [editMode, setEditMode] = useState(false)
  const [searchParams] = useSearchParams()
  const [tmplList, setTmplList] = useState<Template[]>([])
  const [showTemplates, setShowTemplates] = useState(false)
  const [aiGenerating, setAiGenerating] = useState(false)
  const [search, setSearch] = useState('')

  const fetchList = useCallback(() => {
    return documents.list({ page_size: 50 })
  }, [])

  const loadList = useCallback(async () => {
    setLoading(true)
    try {
      const data = await fetchList()
      setList(data.items)
    } catch (e) { console.error('Failed to load documents', e) }
    finally { setLoading(false) }
  }, [fetchList])

  useEffect(() => {
    let active = true
    void fetchList()
      .then(data => { if (active) setList(data.items) })
      .catch(e => { if (active) console.error('Failed to load documents', e) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [fetchList])

  useEffect(() => {
    templates.list().then(setTmplList).catch(() => {})
  }, [])

  const fetchDoc = useCallback((id: string) => documents.get(id), [])

  const openDoc = useCallback(async (id: string) => {
    try {
      const doc = await fetchDoc(id)
      setCurrent(doc)
      setView('editor')
      setEditMode(false)
    } catch (e) { console.error('Failed to load document', e) }
  }, [fetchDoc])

  const editId = searchParams.get('edit')
  useEffect(() => {
    if (!editId) return
    let active = true
    void fetchDoc(editId)
      .then(doc => {
        if (!active) return
        setCurrent(doc)
        setView('editor')
        setEditMode(false)
      })
      .catch(e => { if (active) console.error('Failed to load document', e) })
    return () => { active = false }
  }, [editId, fetchDoc])

  const handleNew = () => {
    setShowTemplates(true)
  }

  const handleCreateFromTemplate = async (templateId: string) => {
    try {
      const doc = await templates.createDocument(templateId)
      setShowTemplates(false)
      await openDoc(doc.id)
      loadList()
    } catch (e) { console.error('Failed to create from template', e) }
  }

  const handleCreateBlank = async () => {
    try {
      const doc = await documents.create({ title: 'Новый документ', type: 'custom' })
      setShowTemplates(false)
      await openDoc(doc.id)
      loadList()
    } catch (e) { console.error('Failed to create document', e) }
  }

  const handleSave = async () => {
    if (!current) return
    try {
      const updated = await documents.update(current.id, { content: current.content })
      setCurrent(updated)
    } catch (e) { console.error('Failed to save', e) }
  }

  const handleDownloadPdf = () => {
    if (!current) return
    window.open(documents.pdfUrl(current.id), '_blank')
  }

  const handleDownloadDocx = () => {
    if (!current) return
    window.open(documents.docxUrl(current.id), '_blank')
  }

  const handleAiGenerate = async () => {
    if (!current) return
    setAiGenerating(true)
    try {
      const res = await ai.generateDocument(current.type, current.title)
      if (res.content) {
        setCurrent({ ...current, content: res.content })
      }
    } catch (e) { console.error('AI generation failed', e) }
    finally { setAiGenerating(false) }
  }

  const handleDelete = async () => {
    if (!current) return
    if (!window.confirm('Удалить документ? Это действие необратимо.')) return
    try {
      await documents.delete(current.id)
      setView('list')
      setCurrent(null)
      loadList()
    } catch (e) { console.error('Failed to delete', e) }
  }

  // --- EDITOR ---
  if (view === 'editor' && current) {
    return (
      <div className="document-page h-full overflow-y-auto">
        <div className="document-editor-shell max-w-[900px] mx-auto px-4 sm:px-6 py-4">
          <header className="document-editor-header">
            <div className="document-editor-identity">
              <button aria-label="К списку документов" onClick={() => { setView('list'); setCurrent(null) }} className="document-editor-icon-button rounded-[var(--radius-md)] hover:bg-[var(--bg-hover)] transition-colors"><ArrowLeft size={18} /></button>
              <h1 className="text-[18px] sm:text-[20px] font-semibold text-[var(--text-primary)] truncate">{current.title}</h1>
              <span className={`document-editor-status px-2 py-0.5 rounded-[var(--radius-pill)] text-[11px] font-medium ${statusLabels[current.status]?.className || ''}`}>{statusLabels[current.status]?.text || current.status}</span>
            </div>
            <div className="document-editor-actions" role="toolbar" aria-label="Действия с документом">
              <button onClick={handleAiGenerate} disabled={aiGenerating} className="document-editor-action border border-[var(--accent-lavender)]/30 text-[var(--accent-lavender)] hover:bg-[var(--accent-lavender)]/10 transition-colors flex items-center gap-1.5 disabled:opacity-50">
                <Sparkles size={14} /> {aiGenerating ? 'Генерация...' : 'AI текст'}
              </button>
              <button onClick={() => setEditMode(!editMode)} className="document-editor-action border border-[var(--border-subtle)] text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] transition-colors">{editMode ? 'Просмотр' : 'Редактировать'}</button>
              {editMode && <button onClick={handleSave} className="document-editor-action bg-[var(--accent-teal)] text-white font-medium hover:bg-[var(--accent-teal-hover)] transition-colors">Сохранить</button>}
              <button onClick={handleDownloadPdf} className="document-editor-action border border-[var(--border-subtle)] text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] transition-colors flex items-center gap-1.5"><Download size={14} /> PDF</button>
              <button onClick={handleDownloadDocx} className="document-editor-action border border-[var(--border-subtle)] text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] transition-colors flex items-center gap-1.5"><FileSpreadsheet size={14} /> DOCX</button>
              <button aria-label="Удалить документ" onClick={handleDelete} className="document-editor-icon-button text-[var(--text-tertiary)] hover:text-red-600 hover:bg-red-50 transition-colors" title="Удалить"><Trash2 size={15} /></button>
            </div>
          </header>

          {editMode ? (
            <textarea value={current.content} onChange={event => setCurrent({ ...current, content: event.target.value })} aria-label="HTML документа" className="document-editor-canvas is-editing min-h-[500px] w-full resize-y p-6 rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] font-mono text-[13px] leading-relaxed outline-none focus:border-[var(--accent-teal)] transition-colors" />
          ) : (
            <iframe title={`Предпросмотр документа: ${current.title}`} sandbox="" referrerPolicy="no-referrer" srcDoc={sandboxedDocumentHtml(current.content)} className="document-editor-canvas is-previewing min-h-[600px] w-full rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-white shadow-sm" />
          )}
        </div>
      </div>
    )
  }

  // --- LIST ---
  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-[1000px] mx-auto px-4 sm:px-6 py-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-6">
          <h1 className="text-[22px] sm:text-[26px] font-semibold text-[var(--text-primary)] tracking-tight">Документы</h1>
          <div className="flex items-center gap-2">
            <div className="relative flex-1 sm:flex-none">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-tertiary)]" />
              <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Поиск..." className="h-9 pl-8 pr-3 w-full sm:w-56 bg-[var(--bg-secondary)] border border-[var(--border-subtle)] rounded-[var(--radius-md)] text-[13px] outline-none focus:border-[var(--accent-teal)] transition-colors" />
            </div>
            <button onClick={handleNew} className="h-9 px-3 bg-[var(--accent-teal)] text-white rounded-[var(--radius-md)] text-[13px] font-medium hover:bg-[var(--accent-teal-hover)] transition-colors flex items-center gap-1.5 flex-shrink-0">
              <Plus size={15} /> <span className="hidden sm:inline">Новый</span>
            </button>
          </div>
        </div>

        {loading ? (
          <div className="text-center py-16 text-[var(--text-tertiary)]">Загрузка...</div>
        ) : list.length === 0 ? (
          <div className="text-center py-16">
            <FileText size={40} className="mx-auto text-[var(--text-tertiary)] mb-3" strokeWidth={1.2} />
            <p className="text-[14px] text-[var(--text-tertiary)]">Документов пока нет</p>
          </div>
        ) : (
          <div className="space-y-2">
            {list.filter(doc => !search || doc.title.toLowerCase().includes(search.toLowerCase())).map(doc => (
              <div key={doc.id} onClick={() => openDoc(doc.id)} className="group flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4 p-4 rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] hover:border-[var(--border-hover)] hover:shadow-[var(--shadow-sm)] transition-all cursor-pointer">
                <div className="w-9 h-9 rounded-[var(--radius-md)] bg-[#f0edfe] text-[#7c6df1] flex items-center justify-center flex-shrink-0"><FileText size={18} strokeWidth={1.8} /></div>
                <div className="flex-1 min-w-0">
                  <h3 className="text-[14px] font-medium text-[var(--text-primary)] truncate group-hover:text-[var(--accent-teal)] transition-colors">{doc.title}</h3>
                  <p className="text-[12px] text-[var(--text-tertiary)]">{typeLabels[doc.type] || doc.type} · {doc.client || '—'} · {formatDate(doc.created_at)}</p>
                </div>
                <span className={`px-2 py-0.5 rounded-[var(--radius-pill)] text-[11px] font-medium flex-shrink-0 ${statusLabels[doc.status]?.className || ''}`}>{statusLabels[doc.status]?.text || doc.status}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Template picker modal */}
      {showTemplates && (
        <div className="fixed inset-0 bg-black/30 z-50 flex items-center justify-center p-4" onClick={() => setShowTemplates(false)}>
          <div className="bg-[var(--bg-primary)] rounded-[var(--radius-xl)] shadow-xl max-w-[500px] w-full p-6 max-h-[80vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
            <h2 className="text-[18px] font-semibold text-[var(--text-primary)] mb-4">Выберите шаблон</h2>
            <div className="space-y-2 mb-4">
              {tmplList.map(t => (
                <button
                  key={t.id}
                  onClick={() => handleCreateFromTemplate(t.id)}
                  className="w-full text-left p-3 rounded-[var(--radius-md)] border border-[var(--border-subtle)] hover:border-[var(--accent-teal)] hover:bg-[var(--bg-hover)] transition-all"
                >
                  <h3 className="text-[14px] font-medium text-[var(--text-primary)]">{t.title}</h3>
                  <p className="text-[12px] text-[var(--text-tertiary)]">{typeLabels[t.type] || t.type}</p>
                </button>
              ))}
            </div>
            <div className="flex gap-2">
              <button onClick={handleCreateBlank} className="flex-1 h-9 rounded-[var(--radius-md)] border border-[var(--border-subtle)] text-[13px] text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] transition-colors">Пустой документ</button>
              <button onClick={() => setShowTemplates(false)} className="h-9 px-3 rounded-[var(--radius-md)] text-[13px] text-[var(--text-tertiary)] hover:bg-[var(--bg-hover)] transition-colors">Отмена</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
