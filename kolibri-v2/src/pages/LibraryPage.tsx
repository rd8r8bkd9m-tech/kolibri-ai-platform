import { useDeferredValue, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router'
import {
  BarChart3,
  Calculator,
  Download,
  FileText,
  FolderOpen,
  Image,
  LayoutGrid,
  List,
  Search,
  Share2,
  Table2,
} from 'lucide-react'
import {
  artifactWorkbooks,
  estimates,
  library,
  type LibraryItem,
  type WorkbookPreview,
} from '@/lib/api'
import EmbeddedImageViewer from '@/features/documents/EmbeddedImageViewer'
import EmbeddedPdfViewer from '@/features/documents/EmbeddedPdfViewer'
import EmbeddedWorkbookViewer from '@/features/documents/EmbeddedWorkbookViewer'
import { shareFile } from '@/features/documents/fileShare'

const filters = [
  { key: 'all', label: 'Все' },
  { key: 'estimate', label: 'Сметы' },
  { key: 'document', label: 'Документы' },
  { key: 'pdf', label: 'PDF' },
  { key: 'table', label: 'Таблицы' },
  { key: 'media', label: 'Медиа' },
  { key: 'report', label: 'Отчёты' },
] as const

const filterLabels: Record<string, string> = Object.fromEntries(filters.map(item => [item.key, item.label]))

const typeIcons: Record<string, { icon: typeof FileText; className: string }> = {
  estimate: { icon: Calculator, className: 'estimate' },
  document: { icon: FileText, className: 'document' },
  pdf: { icon: FileText, className: 'pdf' },
  table: { icon: Table2, className: 'table' },
  media: { icon: Image, className: 'media' },
  report: { icon: BarChart3, className: 'report' },
  agent_result: { icon: BarChart3, className: 'report' },
}

type PreviewState =
  | { kind: 'pdf'; item: LibraryItem }
  | { kind: 'workbook'; item: LibraryItem }
  | { kind: 'image'; item: LibraryItem }
  | null

function readableSize(bytes: number): string {
  if (!bytes) return ''
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} КБ`
  return `${(bytes / 1024 / 1024).toFixed(1)} МБ`
}

function itemSubtitle(item: LibraryItem): string {
  const parts = [
    filterLabels[item.item_type] || item.item_type,
    item.version ? `версия ${item.version}` : '',
    item.project,
    readableSize(item.file_size),
  ].filter(Boolean)
  return parts.join(' · ')
}

function workbookLoader(item: LibraryItem): () => Promise<WorkbookPreview> {
  if (item.source_type === 'estimate_xlsx') {
    return () => estimates.workbook(item.source_id, item.version)
  }
  return () => artifactWorkbooks.preview(item.source_id, item.version)
}

export default function LibraryPage() {
  const [activeFilter, setActiveFilter] = useState('all')
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid')
  const [search, setSearch] = useState('')
  const [items, setItems] = useState<LibraryItem[]>([])
  const [counts, setCounts] = useState<Record<string, number>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [preview, setPreview] = useState<PreviewState>(null)
  const deferredSearch = useDeferredValue(search.trim().toLocaleLowerCase('ru-RU'))
  const navigate = useNavigate()

  useEffect(() => {
    let active = true
    void library.list({ page_size: 100 })
      .then(data => {
        if (!active) return
        setItems(data.items)
        setCounts(data.counts || {})
        setError('')
      })
      .catch(fetchError => {
        if (!active) return
        console.error('Failed to load library', fetchError)
        setError('Файлы не загрузились. Обновите страницу и повторите.')
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => { active = false }
  }, [])

  const visibleItems = useMemo(() => items.filter(item => {
    if (activeFilter !== 'all' && item.item_type !== activeFilter) return false
    if (!deferredSearch) return true
    return [item.title, item.client, item.project, item.filename]
      .some(value => String(value || '').toLocaleLowerCase('ru-RU').includes(deferredSearch))
  }), [activeFilter, deferredSearch, items])

  const openItem = (item: LibraryItem) => {
    setNotice('')
    if (item.source_type === 'estimate') {
      navigate(`/estimates?edit=${encodeURIComponent(item.source_id)}`)
      return
    }
    if (item.source_type === 'document') {
      navigate(`/documents?edit=${encodeURIComponent(item.source_id)}`)
      return
    }
    if (item.item_type === 'pdf' && item.open_url) {
      setPreview({ kind: 'pdf', item })
      return
    }
    if (item.item_type === 'table' && item.open_url) {
      setPreview({ kind: 'workbook', item })
      return
    }
    if (item.item_type === 'media' && item.mime_type?.startsWith('image/') && item.open_url) {
      setPreview({ kind: 'image', item })
      return
    }
    if (item.source_type === 'document_pdf') {
      setPreview({ kind: 'pdf', item })
      return
    }
    setNotice('Для этого формата доступно скачивание файла.')
  }

  const shareItem = async (item: LibraryItem) => {
    const url = item.download_url || item.open_url
    if (!url || !item.mime_type) {
      setNotice('Для этого элемента пока нет готового файла.')
      return
    }
    setNotice('Готовлю файл…')
    try {
      const result = await shareFile({
        url,
        filename: item.filename || item.title,
        mimeType: item.mime_type,
        title: item.title,
      })
      setNotice(result === 'shared' ? 'Файл передан.' : 'Файл скачан.')
    } catch (shareError) {
      if ((shareError as DOMException).name !== 'AbortError') setNotice('Не удалось подготовить файл.')
    }
  }

  return (
    <div className="library-page">
      <div className="library-shell">
        <header className="library-header">
          <div>
            <h1>Файлы</h1>
            <p>Сметы, документы и готовые форматы по вашим объектам</p>
          </div>
          <div className="library-view-toggle" aria-label="Вид файлов">
            <button type="button" aria-label="Плитка" aria-pressed={viewMode === 'grid'} onClick={() => setViewMode('grid')}><LayoutGrid size={18} /></button>
            <button type="button" aria-label="Список" aria-pressed={viewMode === 'list'} onClick={() => setViewMode('list')}><List size={18} /></button>
          </div>
        </header>

        <label className="library-search">
          <Search size={19} />
          <input value={search} onChange={event => setSearch(event.target.value)} placeholder="Найти файл, объект или заказчика" />
        </label>

        <nav className="library-filters" aria-label="Типы файлов" role="tablist">
          {filters.map(filter => (
            <button
              key={filter.key}
              type="button"
              role="tab"
              aria-selected={activeFilter === filter.key}
              className={activeFilter === filter.key ? 'is-active' : ''}
              onClick={() => setActiveFilter(filter.key)}
            >
              <span>{filter.label}</span>
              <small>{counts[filter.key] || 0}</small>
            </button>
          ))}
        </nav>

        {notice && <p className="library-notice" role="status">{notice}</p>}
        {error && <p className="library-error" role="alert">{error}</p>}

        {loading ? (
          <div className="library-state" role="status">Загружаю файлы…</div>
        ) : visibleItems.length === 0 ? (
          <div className="library-state is-empty">
            <FolderOpen size={38} />
            <strong>Здесь пока пусто</strong>
            <p>{activeFilter === 'pdf'
              ? 'Сохраните смету или документ — PDF появится здесь автоматически.'
              : activeFilter === 'table'
                ? 'Сохраните смету — её Excel-версия появится здесь автоматически.'
                : 'Создайте смету, документ или загрузите файл в чате.'}</p>
          </div>
        ) : (
          <div className={`library-items ${viewMode === 'list' ? 'is-list' : ''}`}>
            {visibleItems.map(item => {
              const icon = typeIcons[item.item_type] || typeIcons.document
              const Icon = icon.icon
              return (
                <article className="library-item" key={item.id}>
                  <button type="button" className="library-item-main" onClick={() => openItem(item)}>
                    <span className={`library-item-icon ${icon.className}`}><Icon size={22} /></span>
                    <span className="library-item-copy">
                      <strong>{item.title}</strong>
                      <small>{itemSubtitle(item)}</small>
                      <time dateTime={item.updated_at}>{new Date(item.updated_at || item.created_at).toLocaleDateString('ru-RU')}</time>
                    </span>
                  </button>
                  <footer>
                    <button type="button" onClick={() => openItem(item)}>Открыть</button>
                    {item.download_url && item.mime_type && (
                      <button type="button" aria-label={`Поделиться: ${item.title}`} onClick={() => void shareItem(item)}><Share2 size={17} /></button>
                    )}
                    {item.download_url && (
                      <a href={item.download_url} download={item.filename} aria-label={`Скачать: ${item.title}`}><Download size={17} /></a>
                    )}
                  </footer>
                </article>
              )
            })}
          </div>
        )}
      </div>

      {preview?.kind === 'pdf' && preview.item.open_url && (
        <EmbeddedPdfViewer url={preview.item.open_url} title={preview.item.title} onClose={() => setPreview(null)} />
      )}
      {preview?.kind === 'workbook' && preview.item.download_url && (
        <EmbeddedWorkbookViewer
          title={preview.item.title}
          downloadUrl={preview.item.download_url}
          loadKey={preview.item.id}
          load={workbookLoader(preview.item)}
          onClose={() => setPreview(null)}
        />
      )}
      {preview?.kind === 'image' && preview.item.open_url && preview.item.download_url && (
        <EmbeddedImageViewer
          url={preview.item.open_url}
          downloadUrl={preview.item.download_url}
          title={preview.item.title}
          filename={preview.item.filename || preview.item.title}
          mimeType={preview.item.mime_type || 'application/octet-stream'}
          onClose={() => setPreview(null)}
        />
      )}
    </div>
  )
}
