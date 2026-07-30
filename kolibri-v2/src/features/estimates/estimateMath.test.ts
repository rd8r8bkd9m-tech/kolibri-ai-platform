import { describe, expect, it } from 'vitest'
import type { Estimate } from '@/lib/api'
import {
  deleteEstimatePosition,
  estimateTotalsEqual,
  recalculateEstimate,
  updateEstimatePosition,
  updateEstimatePositionName,
  updateEstimateRate,
} from './estimateMath'

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

  it('renames and deletes a row without leaving stale totals', () => {
    const renamed = updateEstimatePositionName(fixture(), 'section-1', 'position-1', '  Монтаж   кирпича  ')!
    expect(renamed.sections[0].positions[0].name).toBe('Монтаж кирпича')
    expect(updateEstimatePositionName(fixture(), 'section-1', 'position-1', '   ')).toBeNull()

    const removed = deleteEstimatePosition(renamed, 'section-1', 'position-1')
    expect(removed.sections[0].positions).toEqual([])
    expect(removed.sections[0].subtotal).toBe('0.00')
    expect(removed.total).toBe('0.00')
  })

  it('recalculates overhead and VAT when rates change', () => {
    const overhead = updateEstimateRate(fixture(), 'overhead_rate', '15')!
    const vat = updateEstimateRate(overhead, 'vat_rate', '5')!
    expect(vat.overhead_amount).toBe('30.00')
    expect(vat.vat_amount).toBe('11.50')
    expect(vat.total).toBe('241.50')
    expect(updateEstimateRate(fixture(), 'vat_rate', '1000')).toBeNull()
  })

  it('keeps profit, reserve, general contractor fee and discount transparent', () => {
    const withProfit = updateEstimateRate(fixture(), 'profit_rate', '8')!
    const withReserve = updateEstimateRate(withProfit, 'contingency_rate', '2')!
    const withContractor = updateEstimateRate(withReserve, 'general_contractor_rate', '3')!
    const withDiscount = updateEstimateRate(withContractor, 'discount_rate', '1')!

    expect(withDiscount.profit_amount).toBe('17.60')
    expect(withDiscount.contingency_amount).toBe('4.75')
    expect(withDiscount.general_contractor_amount).toBe('7.27')
    expect(withDiscount.discount_amount).toBe('2.50')
    expect(withDiscount.vat_amount).toBe('54.37')
    expect(withDiscount.total).toBe('301.49')
  })
})
