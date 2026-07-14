import { describe, expect, it } from 'vitest'
import type { Estimate, PriceSourceEvidence } from '@/lib/api'
import { estimateEvidenceSummary } from './estimateEvidence'

function verifiedEvidence(overrides: Partial<PriceSourceEvidence> = {}): PriceSourceEvidence {
  return {
    position_code: 'М-1',
    source_id: 'supplier-1',
    url: 'https://supplier.example/prices/brick',
    source_title: 'Прайс поставщика',
    source_type: 'supplier_quote',
    region: 'Республика Татарстан',
    observed_at: '2026-07-14T08:00:00+03:00',
    price_date: '2026-07-14',
    unit: 'шт',
    unit_price: '100.00',
    vat_status: 'с НДС',
    currency: 'RUB',
    content_sha256: 'a'.repeat(64),
    verification: 'verified',
    attestation: 'b'.repeat(64),
    ...overrides,
  }
}

function fixture(): Estimate {
  const evidence = verifiedEvidence()
  return {
    id: '22222222-2222-4222-8222-222222222222',
    version: 1,
    status: 'ready',
    estimate_status: 'source_backed',
    pricing_status: 'source_backed',
    title: 'Смета: дом 100 м²',
    client: '',
    object_name: 'Дом',
    region: 'Лениногорск, Татарстан',
    currency: 'RUB',
    overhead_rate: '0',
    vat_rate: '22',
    subtotal: '200.00',
    overhead_amount: '0.00',
    vat_amount: '44.00',
    total: '244.00',
    price_sources: [evidence],
    assumptions: ['Объём принят по проекту'],
    questions: ['Подтвердите сроки поставки'],
    sections: [{
      id: 'section-1',
      title: 'Материалы',
      subtotal: '200.00',
      positions: [{
        id: 'position-1',
        code: 'М-1',
        name: 'Кирпич',
        unit: 'шт',
        quantity: '2',
        price: '100',
        sum: '200.00',
        source: 'Красивое название без доказательства',
        price_evidence: [evidence],
        comment: '',
      }],
    }],
    created_at: '2026-07-14T00:00:00Z',
    updated_at: '2026-07-14T08:00:00Z',
  }
}

describe('estimate price evidence', () => {
  it('accepts source-backed status only when every priced row has a verified regional binding', () => {
    const summary = estimateEvidenceSummary(fixture())
    expect(summary.pricingStatus).toBe('source_backed')
    expect(summary.estimateStatus).toBe('source_backed')
    expect(summary.verifiedRows).toBe(1)
    expect(summary.totalPricedRows).toBe(1)
    expect(summary.dateLabel).toBe('14.07.2026')
  })

  it('never treats a non-empty legacy source string as evidence', () => {
    const estimate = fixture()
    estimate.sections[0].positions[0].price_evidence = []
    estimate.price_sources = []
    const summary = estimateEvidenceSummary(estimate)
    expect(summary.pricingStatus).toBe('preliminary')
    expect(summary.estimateStatus).toBe('preliminary')
    expect(summary.verifiedRows).toBe(0)
    expect(summary.rows[0].reason).toContain('текст источника')
  })

  it('downgrades a declared verified estimate when the source price does not match the row', () => {
    const estimate = fixture()
    estimate.estimate_status = 'verified'
    estimate.pricing_status = 'verified'
    estimate.sections[0].positions[0].price_evidence = [verifiedEvidence({ unit_price: '101.00' })]
    const summary = estimateEvidenceSummary(estimate)
    expect(summary.pricingStatus).toBe('preliminary')
    expect(summary.estimateStatus).toBe('preliminary')
    expect(summary.rows[0].reason).toContain('не совпадает')
  })

  it('keeps a valid source-backed binding without presenting it as independently verified', () => {
    const estimate = fixture()
    const sourceBacked = verifiedEvidence({ verification: 'source_backed' })
    estimate.sections[0].positions[0].price_evidence = [sourceBacked]
    estimate.price_sources = [sourceBacked]
    estimate.pricing_status = 'source_backed'

    const summary = estimateEvidenceSummary(estimate)

    expect(summary.pricingStatus).toBe('source_backed')
    expect(summary.estimateStatus).toBe('source_backed')
    expect(summary.verifiedRows).toBe(1)
  })

  it('downgrades declared verified pricing to source-backed when independent verification is absent', () => {
    const estimate = fixture()
    const sourceBacked = verifiedEvidence({ verification: 'source_backed' })
    estimate.sections[0].positions[0].price_evidence = [sourceBacked]
    estimate.price_sources = [sourceBacked]
    estimate.pricing_status = 'verified'
    estimate.estimate_status = 'verified'

    const summary = estimateEvidenceSummary(estimate)

    expect(summary.pricingStatus).toBe('source_backed')
    expect(summary.estimateStatus).toBe('source_backed')
  })
})
