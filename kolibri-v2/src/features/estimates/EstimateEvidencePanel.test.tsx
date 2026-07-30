import { afterEach, describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import type { Estimate } from '@/lib/api'
import EstimateEvidencePanel from './EstimateEvidencePanel'

afterEach(() => vi.unstubAllGlobals())

describe('EstimateEvidencePanel', () => {
  it('renders region, price date, bound source, assumptions and questions in the inline surface', () => {
    vi.stubGlobal('localStorage', { getItem: () => null })
    const estimate: Estimate = {
      id: '22222222-2222-4222-8222-222222222222',
      version: 1,
      status: 'ready',
      estimate_status: 'source_backed',
      pricing_status: 'source_backed',
      title: 'Смета: дом',
      client: '',
      object_name: 'Дом',
      region: 'Лениногорск, Татарстан',
      currency: 'RUB',
      overhead_rate: '0',
      vat_rate: '22',
      subtotal: '100.00',
      overhead_amount: '0.00',
      vat_amount: '22.00',
      total: '122.00',
      assumptions: ['Площадь принята по проекту'],
      questions: ['Подтвердите марку материала'],
      sections: [{
        id: 'section-1', title: 'Материалы', subtotal: '100.00', positions: [{
          id: 'position-1', code: 'М-1', name: 'Материал', unit: 'шт', quantity: '1', price: '100', sum: '100.00', source: '', comment: '',
          price_evidence: [{
            position_code: 'М-1',
            source_id: 'source-1',
            url: 'https://supplier.example/material',
            source_title: 'Прайс поставщика Татарстана',
            region: 'Татарстан',
            price_date: '2026-07-14',
            unit: 'шт',
            unit_price: '100',
            currency: 'RUB',
            verification: 'verified',
          }],
        }],
      }],
      created_at: '2026-07-14T00:00:00Z',
      updated_at: '2026-07-14T00:00:00Z',
    }

    const html = renderToStaticMarkup(<EstimateEvidencePanel estimate={estimate} compact />)
    expect(html).toContain('Лениногорск, Татарстан')
    expect(html).toContain('14.07.2026')
    expect(html).toContain('Прайс поставщика Татарстана')
    expect(html).toContain('Площадь принята по проекту')
    expect(html).toContain('Подтвердите марку материала')
    expect(html).toContain('1 из 1 цен')
  })
})
