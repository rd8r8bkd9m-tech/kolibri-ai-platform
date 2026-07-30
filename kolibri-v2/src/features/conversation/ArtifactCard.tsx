import { useCallback, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Archive, Check, Download, ExternalLink, FileDown, FileSpreadsheet, FileText, Image as ImageIcon, Maximize2, PencilLine, Presentation, RotateCw, X } from 'lucide-react'
import { artifactWorkbooks, documents, estimates, type Document, type Estimate, type FileArtifact, type ImageArtifact } from '@/lib/api'
import { formatCurrency } from '@/lib/utils'
import { recalculateEstimate, updateEstimatePosition } from '@/features/estimates/estimateMath'
import { isVerifiedImageArtifact } from './imageArtifact'
import { isVerifiedFileArtifact, type VerifiedFileArtifact } from './fileArtifact'
import { sandboxedDocumentHtml } from '@/features/documents/sandboxedDocument'
import EmbeddedPdfViewer from '@/features/documents/EmbeddedPdfViewer'
import EmbeddedWorkbookViewer from '@/features/documents/EmbeddedWorkbookViewer'

export type ConversationArtifact =
  | { type: 'estimate'; value: Estimate }
  | { type: 'document'; value: Document }
  | { type: 'image'; value: ImageArtifact }
  | { type: 'file'; value: FileArtifact }

interface ArtifactCardProps {
  artifact: ConversationArtifact
  onOpen: () => void
  onRetry?: () => void
  onUpdate?: (artifact: ConversationArtifact) => void
}

function estimateUpdatePayload(estimate: Estimate) {
  return {
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
    sections: estimate.sections.map(section => ({
      title: section.title,
      positions: section.positions.map(position => ({
        code: position.code,
        name: position.name,
        unit: position.unit,
        quantity: position.quantity,
        price: position.price,
        source: position.source,
        source_evidence: position.source_evidence,
        price_evidence: position.price_evidence,
        comment: position.comment,
      })),
    })),
  }
}

function EstimateCard({
  estimate,
  onOpen,
  onUpdate,
}: {
  estimate: Estimate
  onOpen: () => void
  onUpdate?: (estimate: Estimate) => void
}) {
  const [draft, setDraft] = useState(estimate)
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [notice, setNotice] = useState('')
  const status = estimate.estimate_status === 'verified'
    ? 'Проверенная'
    : estimate.estimate_status === 'source_backed'
      ? 'С подтверждёнными ценами'
      : estimate.estimate_status === 'needs_input'
        ? 'Нужны уточнения'
        : 'Предварительная'

  const changePosition = (sectionId: string, positionId: string, field: 'quantity' | 'price', value: string) => {
    const updated = updateEstimatePosition(draft, sectionId, positionId, field, value)
    if (!updated) return
    setDraft(recalculateEstimate(updated))
    setDirty(true)
    setNotice('')
  }

  const save = useCallback(async () => {
    if (!dirty || saving) return
    setSaving(true)
    setNotice('')
    try {
      const updated = await estimates.update(draft.id, estimateUpdatePayload(draft))
      setDraft(updated)
      setDirty(false)
      setNotice('Смета сохранена')
      onUpdate?.(updated)
    } catch {
      setNotice('Не удалось сохранить. Обновите смету и повторите.')
    } finally {
      setSaving(false)
    }
  }, [dirty, draft, onUpdate, saving])

  useEffect(() => {
    if (!dirty || saving) return
    const timeout = window.setTimeout(() => void save(), 900)
    return () => window.clearTimeout(timeout)
  }, [dirty, draft, save, saving])

  return (
    <section
      className="artifact-card conversation-estimate-editor"
      aria-label={estimate.title}
      data-project-case-id={draft.case_id || undefined}
      data-project-id={draft.project_id || undefined}
    >
      <header className="conversation-estimate-editor-header">
        <span><FileText size={24} aria-hidden="true" /></span>
        <div>
          <strong>{draft.title}</strong>
          <small>
            {status} · версия {draft.version}
            {draft.case_id ? ' · сохранена в проектном деле' : ''}
          </small>
        </div>
        <b>{formatCurrency(draft.total)}</b>
      </header>
      <div className="conversation-estimate-editor-meta">
        <span>{draft.object_name || 'Объект не указан'}</span>
        <span>{draft.region || 'Регион не указан'}</span>
      </div>
      <div className="conversation-estimate-editor-sections">
        {draft.sections.map(section => (
          <section key={section.id}>
            <header><strong>{section.title}</strong><span>{formatCurrency(section.subtotal)}</span></header>
            {section.positions.map(position => (
              <div className="conversation-estimate-editor-row" key={position.id}>
                <div><strong>{position.name}</strong><small>{position.code || 'Без кода'} · {position.unit}</small></div>
                <label><span>Объём</span><input disabled={saving} aria-label={`Объём: ${position.name}`} inputMode="decimal" value={position.quantity} onChange={event => changePosition(section.id, position.id, 'quantity', event.target.value)} /></label>
                <label><span>Цена</span><input disabled={saving} aria-label={`Цена: ${position.name}`} inputMode="decimal" value={position.price} onChange={event => changePosition(section.id, position.id, 'price', event.target.value)} /></label>
                <b>{formatCurrency(position.sum)}</b>
              </div>
            ))}
          </section>
        ))}
      </div>
      <footer className="conversation-estimate-editor-actions">
        <button type="button" className="is-secondary" onClick={onOpen}>Подробнее</button>
        <button type="button" disabled={!dirty || saving} onClick={() => void save()}>
          <Check size={17} />{saving ? 'Сохраняю…' : dirty ? 'Сохранить сейчас' : 'Сохранено'}
        </button>
      </footer>
      {(dirty || saving) && (
        <p className="conversation-estimate-editor-notice" role="status">
          {saving ? 'Сохраняю изменения…' : 'Изменения сохранятся автоматически'}
        </p>
      )}
      {notice && <p className="conversation-estimate-editor-notice" role="status">{notice}</p>}
    </section>
  )
}

function DocumentCard({
  document,
  onOpen,
  onPreviewPdf,
}: {
  document: Document
  onOpen: () => void
  onPreviewPdf: () => void
}) {
  return (
    <section className="artifact-card document-artifact" aria-label={document.title}>
      <header className="artifact-card-header">
        <div>
          <span className="artifact-kicker">Редактируемый документ</span>
          <h3>{document.title}</h3>
          <p>{document.type || 'Документ'} · {document.status || 'Черновик'}</p>
        </div>
        <FileText size={26} />
      </header>
      <iframe
        className="artifact-document-preview"
        title={`Предпросмотр документа: ${document.title}`}
        sandbox=""
        referrerPolicy="no-referrer"
        srcDoc={sandboxedDocumentHtml(document.content || '<p>Документ создан. Откройте редактор, чтобы продолжить.</p>')}
      />
      <footer className="artifact-actions">
        <button type="button" onClick={onOpen}><PencilLine size={18} />Редактировать</button>
        <button type="button" onClick={onPreviewPdf}><FileDown size={18} />PDF</button>
        <a href={documents.docxUrl(document.id)} target="_blank" rel="noreferrer"><ExternalLink size={18} />DOCX</a>
      </footer>
    </section>
  )
}

function imageFileName(image: ImageArtifact): string {
  const extension = image.mime_type === 'image/jpeg' ? 'jpg' : image.mime_type.split('/')[1]
  const stem = image.title
    .normalize('NFKC')
    .replace(/[^\p{L}\p{N}._-]+/gu, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 80) || `image-${image.id}`
  return `${stem}.${extension}`
}

function imageSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} КБ`
  return `${(bytes / 1024 / 1024).toFixed(1)} МБ`
}

function FileCard({
  file,
  onOpen,
  onPreviewPdf,
  onPreviewWorkbook,
}: {
  file: FileArtifact
  onOpen: () => void
  onPreviewPdf: () => void
  onPreviewWorkbook: () => void
}) {
  if (!isVerifiedFileArtifact(file)) return null
  const project = file.type === 'site.bundle' || file.type === 'app.bundle'
  const Icon = file.type === 'document.xlsx'
    ? FileSpreadsheet
    : file.type === 'document.pptx'
      ? Presentation
      : project ? Archive : FileText
  const kind = file.type === 'document.pdf'
    ? 'PDF-документ'
    : file.type === 'document.docx'
      ? 'Документ DOCX'
      : file.type === 'document.xlsx'
        ? 'Таблица XLSX'
        : file.type === 'document.pptx'
          ? 'Презентация PPTX'
          : file.type === 'site.bundle' ? 'Проект сайта' : 'Проект приложения'

  return (
    <section className="artifact-card file-artifact" aria-label={file.title}>
      <header className="artifact-card-header">
        <div>
          <span className="artifact-kicker">{kind}</span>
          <h3>{file.title}</h3>
          <p>{file.filename} · {imageSize(file.size_bytes)} · SHA-256 проверен</p>
        </div>
        <Icon size={26} />
      </header>
      {project && file.preview_url && (
        <iframe
          className="artifact-project-preview"
          src={file.preview_url}
          title={`Предпросмотр: ${file.title}`}
          sandbox="allow-scripts"
          referrerPolicy="no-referrer"
        />
      )}
      <footer className="artifact-actions">
        <button
          type="button"
          onClick={file.type === 'document.pdf'
            ? onPreviewPdf
            : file.type === 'document.xlsx' ? onPreviewWorkbook : onOpen}
        >
          <ExternalLink size={18} />{project ? 'Открыть preview' : 'Открыть'}
        </button>
        <a href={file.object_url} download={file.filename}><Download size={18} />Скачать</a>
      </footer>
    </section>
  )
}

function ImageCard({ image, onOpen, onRetry }: { image: ImageArtifact; onOpen: () => void; onRetry?: () => void }) {
  const [fullscreen, setFullscreen] = useState(false)
  const fullscreenButtonRef = useRef<HTMLButtonElement>(null)
  const closeButtonRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (!fullscreen) return
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    closeButtonRef.current?.focus()
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        setFullscreen(false)
      }
    }
    document.addEventListener('keydown', closeOnEscape)
    return () => {
      document.removeEventListener('keydown', closeOnEscape)
      document.body.style.overflow = previousOverflow
    }
  }, [fullscreen])

  if (!isVerifiedImageArtifact(image)) return null
  const fileName = imageFileName(image)
  const closeFullscreen = () => {
    setFullscreen(false)
    window.requestAnimationFrame(() => fullscreenButtonRef.current?.focus())
  }

  return (
    <>
      <section
        className="artifact-card image-artifact"
        aria-label={image.title}
        data-artifact-kind="image"
        data-artifact-id={image.id}
        data-artifact-sha256={image.sha256}
        data-artifact-revision={image.revision}
        data-artifact-reopen-url={image.reopen_url}
        data-artifact-download-url={image.download_url}
      >
        <header className="artifact-card-header">
          <div>
            <span className="artifact-kicker">Изображение</span>
            <h3>{image.title}</h3>
            <p>{imageSize(image.size_bytes)} · байты проверены</p>
          </div>
          <ImageIcon size={26} />
        </header>
        <button type="button" className="artifact-image-preview" onClick={() => setFullscreen(true)} aria-label="Развернуть изображение">
          <img src={image.object_url} alt={image.prompt} loading="eager" />
        </button>
        <footer className="artifact-actions image-artifact-actions">
          <button type="button" data-artifact-open onClick={onOpen}><ExternalLink size={18} />Открыть</button>
          <button ref={fullscreenButtonRef} type="button" onClick={() => setFullscreen(true)}><Maximize2 size={18} />На весь экран</button>
          <a href={image.download_url} download={fileName} data-artifact-download><Download size={18} />Скачать</a>
          {onRetry && <button type="button" onClick={onRetry}><RotateCw size={18} />Повторить</button>}
        </footer>
      </section>
      {fullscreen && typeof document !== 'undefined' && createPortal(
        <div
          className="artifact-image-lightbox"
          role="dialog"
          aria-modal="true"
          aria-label={image.title}
          onMouseDown={event => { if (event.target === event.currentTarget) closeFullscreen() }}
        >
          <header>
            <div><strong>{image.title}</strong><span>{imageSize(image.size_bytes)} · байты проверены</span></div>
            <a href={image.download_url} download={fileName} data-artifact-download><Download size={20} /><span>Скачать</span></a>
            <button ref={closeButtonRef} type="button" aria-label="Закрыть полноэкранный просмотр" onClick={closeFullscreen}><X size={24} /></button>
          </header>
          <img src={image.object_url} alt={image.prompt} />
        </div>,
        document.body,
      )}
    </>
  )
}

export default function ArtifactCard({ artifact, onOpen, onRetry, onUpdate }: ArtifactCardProps) {
  const [pdfPreview, setPdfPreview] = useState<{ url: string; title: string } | null>(null)
  const [workbookPreview, setWorkbookPreview] = useState<VerifiedFileArtifact | null>(null)

  if (artifact.type === 'estimate') return <EstimateCard key={`${artifact.value.id}:${artifact.value.version}`} estimate={artifact.value} onOpen={onOpen} onUpdate={value => onUpdate?.({ type: 'estimate', value })} />
  if (artifact.type === 'document') {
    return (
      <>
        <DocumentCard
          document={artifact.value}
          onOpen={onOpen}
          onPreviewPdf={() => setPdfPreview({
            url: documents.pdfUrl(artifact.value.id),
            title: artifact.value.title,
          })}
        />
        {pdfPreview && <EmbeddedPdfViewer {...pdfPreview} onClose={() => setPdfPreview(null)} />}
      </>
    )
  }
  if (artifact.type === 'file') {
    const file = artifact.value as VerifiedFileArtifact
    return (
      <>
        <FileCard
          file={file}
          onOpen={onOpen}
          onPreviewPdf={() => setPdfPreview({ url: file.object_url, title: file.title })}
          onPreviewWorkbook={() => setWorkbookPreview(file)}
        />
        {pdfPreview && <EmbeddedPdfViewer {...pdfPreview} onClose={() => setPdfPreview(null)} />}
        {workbookPreview && (
          <EmbeddedWorkbookViewer
            title={workbookPreview.title}
            downloadUrl={workbookPreview.object_url}
            loadKey={`${workbookPreview.id}:${workbookPreview.revision}`}
            load={() => artifactWorkbooks.preview(workbookPreview.id, workbookPreview.revision)}
            onClose={() => setWorkbookPreview(null)}
          />
        )}
      </>
    )
  }
  return <ImageCard image={artifact.value} onOpen={onOpen} onRetry={onRetry} />
}
