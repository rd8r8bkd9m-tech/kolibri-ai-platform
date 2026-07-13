import type { Position } from '@/lib/api'
import { formatNum } from '@/lib/utils'

export type EstimateNumericField = 'quantity' | 'price'

export interface EditingEstimateCell {
  secId: string
  posId: string
  field: EstimateNumericField
}

interface EstimatePositionRowProps {
  sectionId: string
  position: Position
  editingCell: EditingEstimateCell | null
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
  onEdit,
  onCommit,
}: EstimatePositionRowProps) {
  const isEditing = (field: EstimateNumericField) => (
    editingCell?.secId === sectionId
    && editingCell.posId === position.id
    && editingCell.field === field
  )
  const sum = Number.parseFloat(position.quantity) * Number.parseFloat(position.price)

  const numericField = (field: EstimateNumericField, value: string, formattedValue: string) => (
    <div className={`estimate-position-field estimate-position-${field}`}>
      <span className="estimate-position-label">{field === 'quantity' ? 'Количество' : 'Цена, ₽'}</span>
      {isEditing(field) ? (
        <input
          autoFocus
          type="text"
          inputMode="decimal"
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
      </div>
      <span className="estimate-position-unit">{position.unit}</span>
      {numericField('quantity', position.quantity, position.quantity)}
      {numericField('price', position.price, formatNum(position.price))}
      <div className="estimate-position-sum">
        <span className="estimate-position-label">Сумма, ₽</span>
        <strong>{formatNum(String(Number.isFinite(sum) ? sum : 0))}</strong>
      </div>
    </div>
  )
}
