import type { Position } from '@/lib/api'
import { formatNum } from '@/lib/utils'
import { useEffect, useState } from 'react'
import { ChevronRight, CircleAlert, Pencil, ShieldCheck, Trash2, X } from 'lucide-react'
import type { PositionEvidenceView } from './estimateEvidence'
import type { EstimateNumericField } from './estimateMath'
import EstimateDecimalInput from './EstimateDecimalInput'
import { visiblePositionComment } from './positionPresentation'

export type { EstimateNumericField } from './estimateMath'

export interface EditingEstimateCell {
  secId: string
  posId: string
  field: EstimateNumericField | 'name'
}

interface EstimatePositionRowProps {
  sectionId: string
  position: Position
  editingCell: EditingEstimateCell | null
  evidence?: PositionEvidenceView
  onEdit: (field: EstimateNumericField | 'name') => void
  onDraft: (field: EstimateNumericField, value: string) => void
  onCommit: (field: EstimateNumericField, value: string) => void
  onNameCommit: (value: string) => void
  onDelete: () => void
}

export default function EstimatePositionRow({
  sectionId,
  position,
  editingCell,
  evidence,
  onEdit,
  onDraft,
  onCommit,
  onNameCommit,
  onDelete,
}: EstimatePositionRowProps) {
  const [mobileOpen, setMobileOpen] = useState(false)

  useEffect(() => {
    if (!mobileOpen) return
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setMobileOpen(false)
    }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [mobileOpen])

  const isEditing = (field: EstimateNumericField | 'name') => (
    editingCell?.secId === sectionId
    && editingCell.posId === position.id
    && editingCell.field === field
  )
  const numericField = (field: EstimateNumericField, value: string, formattedValue: string) => (
    <div className={`estimate-position-field estimate-position-${field}`}>
      <span className="estimate-position-label">{field === 'quantity' ? 'Количество' : 'Цена, ₽'}</span>
      {isEditing(field) ? (
        <EstimateDecimalInput
          autoFocus
          inputMode="decimal"
          maxLength={32}
          enterKeyHint="done"
          value={value}
          aria-label={field === 'quantity' ? `Количество: ${position.name}` : `Цена: ${position.name}`}
          onDraft={draft => onDraft(field, draft)}
          onCommit={committed => onCommit(field, committed)}
          onInvalidDraft={invalid => onCommit(field, invalid)}
          className="estimate-position-input"
        />
      ) : (
        <button
          type="button"
          onClick={() => onEdit(field)}
          className="estimate-position-value"
          aria-label={`Изменить ${field === 'quantity' ? 'количество' : 'цену'}: ${position.name}`}
        >
          {formattedValue}
        </button>
      )}
    </div>
  )

  const evidenceView = evidence && (evidence.verified && evidence.evidence?.url ? (
    <a className="estimate-position-source verified" href={evidence.evidence.url} target="_blank" rel="noreferrer">
      <ShieldCheck size={13} aria-hidden="true" />
      {evidence.evidence.source_title || 'Проверенный источник цены'}
    </a>
  ) : (
    <span className="estimate-position-source unverified">
      <CircleAlert size={13} aria-hidden="true" />{evidence.reason}
    </span>
  ))

  const fullEditor = (
    <>
      <span className="estimate-position-code">{position.code || '—'}</span>
      <div className="estimate-position-name-wrap">
        {isEditing('name') ? (
          <input
            autoFocus
            type="text"
            maxLength={500}
            defaultValue={position.name}
            aria-label={`Наименование позиции: ${position.name}`}
            onBlur={event => onNameCommit(event.target.value)}
            onKeyDown={event => {
              if (event.key === 'Enter') {
                event.preventDefault()
                event.currentTarget.blur()
              }
            }}
            className="estimate-position-name-input"
          />
        ) : (
          <button
            type="button"
            className="estimate-position-name-button"
            onClick={() => onEdit('name')}
            aria-label={`Изменить наименование: ${position.name}`}
          >
            <span className="estimate-position-name">{position.name}</span>
            <Pencil size={13} aria-hidden="true" />
          </button>
        )}
        <span className="estimate-position-unit-mobile">Ед.: {position.unit}</span>
        {visiblePositionComment(position.comment) && (
          <p className="estimate-position-comment">{visiblePositionComment(position.comment)}</p>
        )}
        {evidenceView}
      </div>
      <span className="estimate-position-unit">{position.unit}</span>
      {numericField('quantity', position.quantity, position.quantity)}
      {numericField('price', position.price, formatNum(position.price))}
      <div className="estimate-position-sum">
        <span className="estimate-position-label">Сумма, ₽</span>
        <strong>{formatNum(position.sum)}</strong>
      </div>
      <button
        type="button"
        className="estimate-position-delete"
        onClick={onDelete}
        aria-label={`Удалить позицию: ${position.name}`}
        title="Удалить позицию"
      >
        <Trash2 size={15} aria-hidden="true" />
      </button>
    </>
  )

  return (
    <>
      <div className="estimate-position-row estimate-position-desktop">
        {fullEditor}
      </div>

      <button
        type="button"
        className="estimate-position-mobile-card"
        onClick={() => setMobileOpen(true)}
        aria-label={`Открыть позицию: ${position.name}`}
      >
        <span className="estimate-position-mobile-main">
          <strong>{position.name}</strong>
          <small>{position.quantity} {position.unit} × {formatNum(position.price)} ₽</small>
        </span>
        <span className="estimate-position-mobile-total">
          <strong>{formatNum(position.sum)} ₽</strong>
          <ChevronRight size={18} aria-hidden="true" />
        </span>
      </button>

      {mobileOpen && (
        <div className="estimate-position-sheet-layer" role="presentation">
          <button type="button" className="estimate-position-sheet-backdrop" aria-label="Закрыть позицию" onClick={() => setMobileOpen(false)} />
          <section className="estimate-position-sheet" role="dialog" aria-modal="true" aria-label={`Редактирование позиции: ${position.name}`}>
            <div className="estimate-position-sheet-handle" aria-hidden="true" />
            <header>
              <div>
                <span>Позиция сметы</span>
                <strong>{position.code || 'Без кода'}</strong>
              </div>
              <button type="button" aria-label="Закрыть" onClick={() => setMobileOpen(false)}><X size={20} /></button>
            </header>
            <div className="estimate-position-sheet-scroll">
              <div className="estimate-position-row estimate-position-sheet-editor">
                {fullEditor}
              </div>
            </div>
            <footer>
              <div><span>Сумма</span><strong>{formatNum(position.sum)} ₽</strong></div>
              <button type="button" onClick={() => setMobileOpen(false)}>Готово</button>
            </footer>
          </section>
        </div>
      )}
    </>
  )
}
