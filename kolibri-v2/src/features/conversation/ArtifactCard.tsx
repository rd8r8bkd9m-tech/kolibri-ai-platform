import { useMemo, useState } from 'react'
import { Download, ExternalLink, FileDown, FileText, Image as ImageIcon, Link2, PencilLine } from 'lucide-react'
import { documents, estimates, type Document, type Estimate, type ImageArtifact } from '@/lib/api'
import { formatCurrency } from '@/lib/utils'

export type ConversationArtifact =
  | { type: 'estimate'; value: Estimate }
  | { type: 'document'; value: Document }
  | { type: 'image'; value: ImageArtifact }

interface ArtifactCardProps {
  artifact: ConversationArtifact
  onOpen: () => void
}

function EstimateCard({ estimate, onOpen }: { estimate: Estimate; onOpen: () => void }) {
  const [sourcesOpen, setSourcesOpen] = useState(false)
  const rows = useMemo(() => estimate.sections.flatMap(section => section.positions.map(position => ({ section: section.title, ...position }))), [estimate])
  const sources = useMemo(() => Array.from(new Set(rows.map(row => row.source).filter(Boolean))), [rows])

  return (
    <section className="artifact-card estimate-artifact" aria-label={estimate.title}>
      <header className="artifact-card-header">
        <div>
          <span className="artifact-kicker">Предварительная смета</span>
          <h3>{estimate.title}</h3>
          <p>{[estimate.region, `версия ${estimate.version}`].filter(Boolean).join(' · ')}</p>
        </div>
        <span className="artifact-status">{sources.length ? 'С источниками' : 'Предварительно'}</span>
      </header>

      <div className="artifact-estimate-table" role="table" aria-label="Позиции сметы">
        <div className="artifact-estimate-row artifact-estimate-head" role="row">
          <span>Работы и материалы</span><span>Кол-во</span><span>Цена</span><span>Сумма</span>
        </div>
        {rows.slice(0, 7).map(row => (
          <div key={row.id} className="artifact-estimate-row" role="row">
            <span><strong>{row.name}</strong><small>{row.section} · {row.unit}</small></span>
            <span>{row.quantity}</span>
            <span>{formatCurrency(row.price)}</span>
            <span>{formatCurrency(row.sum)}</span>
          </div>
        ))}
      </div>

      <div className="artifact-mobile-summary">
        {estimate.sections.slice(0, 4).map(section => (
          <div key={section.id}><span>{section.title}</span><strong>{formatCurrency(section.subtotal)}</strong></div>
        ))}
      </div>

      <div className="artifact-total"><span>Итого</span><strong>{formatCurrency(estimate.total)}</strong></div>
      <p className={`artifact-source-status ${sources.length ? 'verified' : 'preliminary'}`}>
        {sources.length ? `Источники указаны для ${sources.length} позиций` : 'Цены требуют подтверждения актуальными региональными источниками'}
      </p>

      {sourcesOpen && (
        <div className="artifact-sources">
          {sources.length ? sources.map(source => <p key={source}>{source}</p>) : <p>Подтверждённые источники ещё не приложены.</p>}
        </div>
      )}

      <footer className="artifact-actions">
        <button type="button" onClick={onOpen}><PencilLine size={18} />Редактировать</button>
        <button type="button" onClick={() => setSourcesOpen(value => !value)}><Link2 size={18} />Источники</button>
        <a href={estimates.pdfUrl(estimate.id)} target="_blank" rel="noreferrer"><FileDown size={18} />PDF</a>
      </footer>
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

function ImageCard({ image, onOpen }: { image: ImageArtifact; onOpen: () => void }) {
  return (
    <section className="artifact-card image-artifact" aria-label={image.title}>
      <header className="artifact-card-header">
        <div>
          <span className="artifact-kicker">Изображение</span>
          <h3>{image.title}</h3>
          <p>{image.model} · {(image.size_bytes / 1024 / 1024).toFixed(1)} МБ</p>
        </div>
        <ImageIcon size={26} />
      </header>
      <button type="button" className="artifact-image-preview" onClick={onOpen} aria-label="Открыть изображение">
        <img src={image.url} alt={image.prompt} loading="lazy" />
      </button>
      <footer className="artifact-actions">
        <button type="button" onClick={onOpen}><ExternalLink size={18} />Открыть</button>
        <a href={image.download_url} download><Download size={18} />Скачать</a>
      </footer>
    </section>
  )
}

export default function ArtifactCard({ artifact, onOpen }: ArtifactCardProps) {
  if (artifact.type === 'estimate') return <EstimateCard estimate={artifact.value} onOpen={onOpen} />
  if (artifact.type === 'document') return <DocumentCard document={artifact.value} onOpen={onOpen} />
  return <ImageCard image={artifact.value} onOpen={onOpen} />
}
