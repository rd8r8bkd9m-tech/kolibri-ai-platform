import { useState, useEffect, useCallback } from 'react'
import { FileText, Search, Plus, ArrowLeft, Bold, Italic, Underline, List, ListOrdered, Download, FileSpreadsheet, Sparkles, Trash2 } from 'lucide-react'
import { useSearchParams } from 'react-router'
import { documents, templates, ai, type Document as Doc, type Template } from '@/lib/api'
import { formatDate } from '@/lib/utils'

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

  const loadList = useCallback(async () => {
    setLoading(true)
    try {
      const data = await documents.list({ page_size: 50 })
      setList(data.items)
    } catch (e) { console.error('Failed to load documents', e) }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { loadList() }, [loadList])

  useEffect(() => {
    templates.list().then(setTmplList).catch(() => {})
  }, [])

  useEffect(() => {
    const editId = searchParams.get('edit')
    if (editId) openDoc(editId)
  }, [searchParams])

  const openDoc = async (id: string) => {
    try {
      const doc = await documents.get(id)
      setCurrent(doc)
      setView('editor')
      setEditMode(false)
    } catch (e) { console.error('Failed to load document', e) }
  }

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
      const el = document.querySelector('[contenteditable]')
      const html = el ? (el as HTMLElement).innerHTML : current.content
      const updated = await documents.update(current.id, { content: html })
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
      <div className="h-full overflow-y-auto">
        <div className="max-w-[900px] mx-auto px-4 sm:px-6 py-4">
          <div className="flex items-center gap-3 mb-4">
            <button onClick={() => { setView('list'); setCurrent(null) }} className="w-8 h-8 flex items-center justify-center rounded-[var(--radius-md)] hover:bg-[var(--bg-hover)] transition-colors"><ArrowLeft size={18} /></button>
            <h1 className="text-[18px] sm:text-[20px] font-semibold text-[var(--text-primary)] truncate">{current.title}</h1>
            <span className={`px-2 py-0.5 rounded-[var(--radius-pill)] text-[11px] font-medium ${statusLabels[current.status]?.className || ''}`}>{statusLabels[current.status]?.text || current.status}</span>
            <div className="ml-auto flex gap-2">
              <button onClick={handleAiGenerate} disabled={aiGenerating} className="h-8 px-3 rounded-[var(--radius-md)] border border-[var(--accent-lavender)]/30 text-[13px] text-[var(--accent-lavender)] hover:bg-[var(--accent-lavender)]/10 transition-colors flex items-center gap-1.5 disabled:opacity-50">
                <Sparkles size={14} /> {aiGenerating ? 'Генерация...' : 'AI текст'}
              </button>
              <button onClick={() => setEditMode(!editMode)} className="h-8 px-3 rounded-[var(--radius-md)] border border-[var(--border-subtle)] text-[13px] text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] transition-colors">{editMode ? 'Просмотр' : 'Редактировать'}</button>
              {editMode && <button onClick={handleSave} className="h-8 px-3 rounded-[var(--radius-md)] bg-[var(--accent-teal)] text-white text-[13px] font-medium hover:bg-[var(--accent-teal-hover)] transition-colors">Сохранить</button>}
              <button onClick={handleDownloadPdf} className="h-8 px-3 rounded-[var(--radius-md)] border border-[var(--border-subtle)] text-[13px] text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] transition-colors flex items-center gap-1.5"><Download size={14} /> PDF</button>
              <button onClick={handleDownloadDocx} className="h-8 px-3 rounded-[var(--radius-md)] border border-[var(--border-subtle)] text-[13px] text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] transition-colors flex items-center gap-1.5"><FileSpreadsheet size={14} /> DOCX</button>
              <button onClick={handleDelete} className="w-8 h-8 flex items-center justify-center rounded-[var(--radius-md)] text-[var(--text-tertiary)] hover:text-red-600 hover:bg-red-50 transition-colors" title="Удалить"><Trash2 size={15} /></button>
            </div>
          </div>

          {editMode && (
            <div className="flex items-center gap-1 p-2 mb-3 rounded-[var(--radius-md)] bg-[var(--bg-secondary)] border border-[var(--border-subtle)]">
              {[{ icon: Bold, cmd: 'bold' }, { icon: Italic, cmd: 'italic' }, { icon: Underline, cmd: 'underline' }, { icon: List, cmd: 'insertUnorderedList' }, { icon: ListOrdered, cmd: 'insertOrderedList' }].map(({ icon: Icon, cmd }) => (
                <button key={cmd} onClick={() => document.execCommand(cmd)} className="w-8 h-8 flex items-center justify-center rounded-[var(--radius-sm)] text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)] transition-colors"><Icon size={15} /></button>
              ))}
            </div>
          )}

          {editMode ? (
            <div contentEditable suppressContentEditableWarning className="min-h-[500px] p-6 rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] text-[14px] leading-relaxed outline-none focus:border-[var(--accent-teal)] transition-colors" dangerouslySetInnerHTML={{ __html: current.content }} />
          ) : (
            <div className="p-6 sm:p-10 rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-white shadow-sm" dangerouslySetInnerHTML={{ __html: current.content.replace(/<h2>/g, '<h2 style="font-size:18px;font-weight:700;margin-bottom:16px;">').replace(/<h3>/g, '<h3 style="font-size:15px;font-weight:600;margin:20px 0 8px;">').replace(/<p>/g, '<p style="margin-bottom:8px;line-height:1.7;color:#374151;">') }} />
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
