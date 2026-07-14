import { describe, expect, it } from 'vitest'
import type { Estimate } from '@/lib/api'
import { estimateTotalsEqual, recalculateEstimate, updateEstimatePosition } from './estimateMath'

function fixture(): Estimate {
  return {
    id: '22222222-2222-4222-8222-222222222222',
    version: 1,
    status: 'draft',
    title: 'Смета: дом',
    client: '',
    object_name: 'Дом',
    region: 'Лениногорск, Татарстан',
    currency: 'RUB',
    overhead_rate: '10',
    vat_rate: '22',
    subtotal: '200.00',
    overhead_amount: '20.00',
    vat_amount: '48.40',
    total: '268.40',
    sections: [{
      id: 'section-1',
      title: 'Работы',
      subtotal: '200.00',
      positions: [{
        id: 'position-1',
        code: 'Р-1',
        name: 'Монтаж',
        unit: 'шт',
        quantity: '2',
        price: '100',
        sum: '200.00',
        source: '',
        comment: '',
      }],
    }],
    created_at: '2026-07-14T00:00:00Z',
    updated_at: '2026-07-14T00:00:00Z',
  }
}

describe('deterministic estimate editor arithmetic', () => {
  it('updates row, section, overhead, VAT and total immediately after quantity and price edits', () => {
    const quantityEdit = updateEstimatePosition(fixture(), 'section-1', 'position-1', 'quantity', '3')
    expect(quantityEdit).not.toBeNull()
    expect(quantityEdit?.sections[0].positions[0].sum).toBe('300.00')
    expect(quantityEdit?.sections[0].subtotal).toBe('300.00')
    expect(quantityEdit?.subtotal).toBe('300.00')
    expect(quantityEdit?.overhead_amount).toBe('30.00')
    expect(quantityEdit?.vat_amount).toBe('72.60')
    expect(quantityEdit?.total).toBe('402.60')

    const priceEdit = updateEstimatePosition(quantityEdit!, 'section-1', 'position-1', 'price', '125')
    expect(priceEdit?.sections[0].positions[0].sum).toBe('375.00')
    expect(priceEdit?.sections[0].subtotal).toBe('375.00')
    expect(priceEdit?.subtotal).toBe('375.00')
    expect(priceEdit?.overhead_amount).toBe('37.50')
    expect(priceEdit?.vat_amount).toBe('90.75')
    expect(priceEdit?.total).toBe('503.25')
  })

  it('uses decimal half-up rounding and matches the server response totals after save', () => {
    const edited = updateEstimatePosition(fixture(), 'section-1', 'position-1', 'quantity', '1,005')!
    const priced = updateEstimatePosition(edited, 'section-1', 'position-1', 'price', '99.995')!
    const serverResponse = recalculateEstimate({ ...priced, version: 2 })

    expect(priced.sections[0].positions[0].sum).toBe('100.49')
    expect(priced.total).toBe('134.86')
    expect(estimateTotalsEqual(priced, serverResponse)).toBe(true)
    expect(estimateTotalsEqual(priced, { ...serverResponse, total: '134.85' })).toBe(false)
  })

  it('rejects invalid numeric input instead of producing NaN', () => {
    expect(updateEstimatePosition(fixture(), 'section-1', 'position-1', 'price', 'сто')).toBeNull()
    expect(updateEstimatePosition(fixture(), 'section-1', 'position-1', 'quantity', '-1')).toBeNull()
  })

  it('does not lose kopecks above the JavaScript safe-integer boundary', () => {
    const quantityEdit = updateEstimatePosition(
      fixture(),
      'section-1',
      'position-1',
      'quantity',
      '9007199254740993',
    )!
    const priceEdit = updateEstimatePosition(
      quantityEdit,
      'section-1',
      'position-1',
      'price',
      '0.01',
    )!

    expect(priceEdit.sections[0].positions[0].sum).toBe('90071992547409.93')
    expect(priceEdit.subtotal).toBe('90071992547409.93')
  })
})
