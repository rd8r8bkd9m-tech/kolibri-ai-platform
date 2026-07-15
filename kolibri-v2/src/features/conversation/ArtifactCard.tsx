import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Archive, Download, ExternalLink, FileDown, FileSpreadsheet, FileText, Image as ImageIcon, Maximize2, PencilLine, Presentation, RotateCw, X } from 'lucide-react'
import { documents, type Document, type Estimate, type FileArtifact, type ImageArtifact } from '@/lib/api'
import { formatCurrency } from '@/lib/utils'
import { isVerifiedImageArtifact } from './imageArtifact'
import { isVerifiedFileArtifact, type VerifiedFileArtifact } from './fileArtifact'

export type ConversationArtifact =
  | { type: 'estimate'; value: Estimate }
  | { type: 'document'; value: Document }
  | { type: 'image'; value: ImageArtifact }
  | { type: 'file'; value: FileArtifact }

interface ArtifactCardProps {
  artifact: ConversationArtifact
  onOpen: () => void
  onRetry?: () => void
}

function EstimateCard({ estimate, onOpen }: { estimate: Estimate; onOpen: () => void }) {
  const status = estimate.estimate_status === 'verified'
    ? 'Проверенная'
    : estimate.estimate_status === 'source_backed'
      ? 'С подтверждёнными ценами'
      : estimate.estimate_status === 'needs_input'
        ? 'Нужны уточнения'
        : 'Предварительная'

  return (
    <section className="artifact-card estimate-artifact artifact-result-card" aria-label={estimate.title}>
      <button type="button" className="artifact-result-row" onClick={onOpen}>
        <FileText className="artifact-result-icon" size={27} strokeWidth={1.7} />
        <span className="artifact-result-copy">
          <strong>{estimate.title}</strong>
          <small>{status}</small>
        </span>
        <span className="artifact-result-action">
          <strong>{formatCurrency(estimate.total)}</strong>
          <i aria-hidden="true" />
          <small>Открыть</small>
        </span>
      </button>
    </section>
  )
}

function DocumentCard({ document, onOpen }: { document: Document; onOpen: () => void }) {
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
      <div className="artifact-document-preview" dangerouslySetInnerHTML={{ __html: document.content || '<p>Документ создан. Откройте редактор, чтобы продолжить.</p>' }} />
      <footer className="artifact-actions">
        <button type="button" onClick={onOpen}><PencilLine size={18} />Редактировать</button>
        <a href={documents.pdfUrl(document.id)} target="_blank" rel="noreferrer"><FileDown size={18} />PDF</a>
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

function FileCard({ file, onOpen }: { file: FileArtifact; onOpen: () => void }) {
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
        <button type="button" onClick={onOpen}><ExternalLink size={18} />{project ? 'Открыть preview' : 'Открыть'}</button>
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

export default function ArtifactCard({ artifact, onOpen, onRetry }: ArtifactCardProps) {
  if (artifact.type === 'estimate') return <EstimateCard estimate={artifact.value} onOpen={onOpen} />
  if (artifact.type === 'document') return <DocumentCard document={artifact.value} onOpen={onOpen} />
  if (artifact.type === 'file') return <FileCard file={artifact.value as VerifiedFileArtifact} onOpen={onOpen} />
  return <ImageCard image={artifact.value} onOpen={onOpen} onRetry={onRetry} />
}
