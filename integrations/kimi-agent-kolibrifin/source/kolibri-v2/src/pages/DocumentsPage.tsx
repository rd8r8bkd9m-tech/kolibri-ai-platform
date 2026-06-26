import { useState } from 'react'
import { FileText, Search, Plus, ArrowLeft, Bold, Italic, Underline, List, ListOrdered } from 'lucide-react'

const docs = [
  { id: 'd1', title: 'Договор подряда №45/2026', type: 'Договор', client: 'ООО СтройПро', status: 'final', date: '24.06.2026' },
  { id: 'd2', title: 'Акт выполненных работ', type: 'Акт', client: 'Иванов И.И.', status: 'final', date: '22.06.2026' },
  { id: 'd3', title: 'Коммерческое предложение', type: 'КП', client: 'Петров С.А.', status: 'draft', date: '20.06.2026' },
  { id: 'd4', title: 'Технический отчёт', type: 'Отчёт', client: 'ООО ТехноСервис', status: 'draft', date: '15.06.2026' },
  { id: 'd5', title: 'Претензионное письмо', type: 'Письмо', client: 'ООО Безопасность', status: 'review', date: '10.06.2026' },
]

const statusLabels: Record<string, { text: string; className: string }> = {
  draft: { text: 'Черновик', className: 'bg-gray-100 text-gray-600' },
  review: { text: 'На согласовании', className: 'bg-[#fef3e8] text-[#f59e0b]' },
  final: { text: 'Финал', className: 'bg-[#e8f8f7] text-[#3ABAB4]' },
}

const TEMPLATE = `<h2>ДОГОВОР ПОДРЯДА № 45/2026</h2>
<p><strong>г. Москва</strong> &nbsp; <strong>«24» июня 2026 г.</strong></p>
<p>&nbsp;</p>
<p>ООО «СтройПро», именуемое в дальнейшем «Заказчик», в лице генерального директора Иванова Ивана Ивановича, действующего на основании Устава, с одной стороны, и Иванов Иван Иванович, именуемый в дальнейшем «Исполнитель», с другой стороны, совместно именуемые «Стороны», заключили настоящий договор о нижеследующем:</p>
<p>&nbsp;</p>
<h3>1. ПРЕДМЕТ ДОГОВОРА</h3>
<p>1.1. Исполнитель обязуется выполнить работы по электромонтажу в жилом доме площадью 120 м² (далее — «Объект»), а Заказчик обязуется принять и оплатить выполненные работы.</p>
<p>1.2. Перечень работ и материалов указан в Приложении №1 (Смета), являющемся неотъемлемой частью настоящего договора.</p>
<p>&nbsp;</p>
<h3>2. СТОИМОСТЬ РАБОТ И ПОРЯДОК РАСЧЁТОВ</h3>
<p>2.1. Общая стоимость работ составляет <strong>290 027,70 (двести девяносто тысяч двадцать семь рублей 70 копеек) рублей</strong>, включая НДС 20%.</p>
<p>2.2. Аванс в размере 50% от общей стоимости уплачивается в течение 3 банковских дней с момента подписания договора.</p>
<p>2.3. Окончательный расчёт производится в течение 5 банковских дней после подписания акта выполненных работ.</p>`

export default function DocumentsPage() {
  const [view, setView] = useState<'list' | 'editor'>('list')
  const [content, setContent] = useState(TEMPLATE)
  const [editMode, setEditMode] = useState(false)

  if (view === 'editor') {
    return (
      <div className="h-full overflow-y-auto">
        <div className="max-w-[900px] mx-auto px-4 sm:px-6 py-4">
          <div className="flex items-center gap-3 mb-4">
            <button onClick={() => setView('list')} className="w-8 h-8 flex items-center justify-center rounded-[var(--radius-md)] hover:bg-[var(--bg-hover)] transition-colors"><ArrowLeft size={18} /></button>
            <h1 className="text-[18px] sm:text-[20px] font-semibold text-[var(--text-primary)] truncate">Договор подряда №45/2026</h1>
            <span className={`px-2 py-0.5 rounded-[var(--radius-pill)] text-[11px] font-medium ${statusLabels.final.className}`}>{statusLabels.final.text}</span>
            <div className="ml-auto flex gap-2">
              <button onClick={() => setEditMode(!editMode)} className="h-8 px-3 rounded-[var(--radius-md)] border border-[var(--border-subtle)] text-[13px] text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] transition-colors">{editMode ? 'Просмотр' : 'Редактировать'}</button>
              <button className="h-8 px-3 rounded-[var(--radius-md)] bg-[var(--accent-teal)] text-white text-[13px] font-medium hover:bg-[var(--accent-teal-hover)] transition-colors">PDF</button>
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
            <div contentEditable suppressContentEditableWarning className="min-h-[500px] p-6 rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] text-[14px] leading-relaxed outline-none focus:border-[var(--accent-teal)] transition-colors" dangerouslySetInnerHTML={{ __html: content }} />
          ) : (
            <div className="p-6 sm:p-10 rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-white shadow-sm" dangerouslySetInnerHTML={{ __html: content.replace(/<h2>/g, '<h2 style="font-size:18px;font-weight:700;margin-bottom:16px;">').replace(/<h3>/g, '<h3 style="font-size:15px;font-weight:600;margin:20px 0 8px;">').replace(/<p>/g, '<p style="margin-bottom:8px;line-height:1.7;color:#374151;">') }} />
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-[1000px] mx-auto px-4 sm:px-6 py-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-6">
          <h1 className="text-[22px] sm:text-[26px] font-semibold text-[var(--text-primary)] tracking-tight">Документы</h1>
          <div className="flex items-center gap-2">
            <div className="relative flex-1 sm:flex-none">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-tertiary)]" />
              <input placeholder="Поиск..." className="h-9 pl-8 pr-3 w-full sm:w-56 bg-[var(--bg-secondary)] border border-[var(--border-subtle)] rounded-[var(--radius-md)] text-[13px] outline-none focus:border-[var(--accent-teal)] transition-colors" />
            </div>
            <button onClick={() => setView('editor')} className="h-9 px-3 bg-[var(--accent-teal)] text-white rounded-[var(--radius-md)] text-[13px] font-medium hover:bg-[var(--accent-teal-hover)] transition-colors flex items-center gap-1.5 flex-shrink-0">
              <Plus size={15} /> <span className="hidden sm:inline">Новый</span>
            </button>
          </div>
        </div>

        <div className="space-y-2">
          {docs.map(doc => (
            <div key={doc.id} onClick={() => setView('editor')} className="group flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4 p-4 rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] hover:border-[var(--border-hover)] hover:shadow-[var(--shadow-sm)] transition-all cursor-pointer">
              <div className="w-9 h-9 rounded-[var(--radius-md)] bg-[#f0edfe] text-[#7c6df1] flex items-center justify-center flex-shrink-0"><FileText size={18} strokeWidth={1.8} /></div>
              <div className="flex-1 min-w-0">
                <h3 className="text-[14px] font-medium text-[var(--text-primary)] truncate group-hover:text-[var(--accent-teal)] transition-colors">{doc.title}</h3>
                <p className="text-[12px] text-[var(--text-tertiary)]">{doc.type} · {doc.client} · {doc.date}</p>
              </div>
              <span className={`px-2 py-0.5 rounded-[var(--radius-pill)] text-[11px] font-medium flex-shrink-0 ${statusLabels[doc.status]?.className || ''}`}>{statusLabels[doc.status]?.text}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
