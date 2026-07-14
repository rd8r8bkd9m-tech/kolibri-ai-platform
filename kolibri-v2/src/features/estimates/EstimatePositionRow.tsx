import type { Position } from '@/lib/api'
import { formatNum } from '@/lib/utils'
import { CircleAlert, ShieldCheck } from 'lucide-react'
import type { PositionEvidenceView } from './estimateEvidence'
import type { EstimateNumericField } from './estimateMath'

export type { EstimateNumericField } from './estimateMath'

export interface EditingEstimateCell {
  secId: string
  posId: string
  field: EstimateNumericField
}

interface EstimatePositionRowProps {
  sectionId: string
  position: Position
  editingCell: EditingEstimateCell | null
  evidence?: PositionEvidenceView
  onEdit: (field: EstimateNumericField) => void
  onCommit: (field: EstimateNumericField, value: string) => void
}

function normalizeDecimal(value: string) {
  return value.trim().replace(',', '.')
}

export default function EstimatePositionRow({
  sectionId,
  position,
  editingCell,
  evidence,
  onEdit,
  onCommit,
}: EstimatePositionRowProps) {
  const isEditing = (field: EstimateNumericField) => (
    editingCell?.secId === sectionId
    && editingCell.posId === position.id
    && editingCell.field === field
  )
  const numericField = (field: EstimateNumericField, value: string, formattedValue: string) => (
    <div className={`estimate-position-field estimate-position-${field}`}>
      <span className="estimate-position-label">{field === 'quantity' ? 'Количество' : 'Цена, ₽'}</span>
      {isEditing(field) ? (
        <input
          autoFocus
          type="text"
          inputMode="decimal"
          maxLength={32}
          enterKeyHint="done"
          defaultValue={value}
          aria-label={field === 'quantity' ? `Количество: ${position.name}` : `Цена: ${position.name}`}
          onBlur={event => onCommit(field, normalizeDecimal(event.target.value))}
          onKeyDown={event => {
            if (event.key === 'Enter') {
              event.preventDefault()
              event.currentTarget.blur()
            }
          }}
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

  return (
    <div className="estimate-position-row">
      <span className="estimate-position-code">{position.code || '—'}</span>
      <div className="estimate-position-name-wrap">
        <span className="estimate-position-name">{position.name}</span>
        <span className="estimate-position-unit-mobile">Ед.: {position.unit}</span>
        {evidence && (evidence.verified && evidence.evidence?.url ? (
          <a className="estimate-position-source verified" href={evidence.evidence.url} target="_blank" rel="noreferrer">
            <ShieldCheck size={13} aria-hidden="true" />
            {evidence.evidence.source_title || 'Проверенный источник цены'}
          </a>
        ) : (
          <span className="estimate-position-source unverified">
            <CircleAlert size={13} aria-hidden="true" />{evidence.reason}
          </span>
        ))}
      </div>
      <span className="estimate-position-unit">{position.unit}</span>
      {numericField('quantity', position.quantity, position.quantity)}
      {numericField('price', position.price, formatNum(position.price))}
      <div className="estimate-position-sum">
        <span className="estimate-position-label">Сумма, ₽</span>
        <strong>{formatNum(position.sum)}</strong>
      </div>
    </div>
  )
}
