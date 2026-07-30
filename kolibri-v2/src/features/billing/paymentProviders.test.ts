import { describe, expect, it } from 'vitest'
import { PAYMENT_PROVIDER_PLACEHOLDERS, paymentProviderStatus } from './paymentProviders'

describe('payment provider placeholders', () => {
  it('lists the three planned Russian payment routes without enabling configuration', () => {
    expect(PAYMENT_PROVIDER_PLACEHOLDERS.map(provider => provider.id)).toEqual(['tbank', 'yookassa', 'sbp'])
    for (const provider of PAYMENT_PROVIDER_PLACEHOLDERS) {
      expect(provider.status).toBe('not_connected')
      expect(provider.configurationAvailable).toBe(false)
      expect(paymentProviderStatus(provider)).toBe('Не подключено')
    }
  })

  it('contains no credential-shaped fields or checkout URL', () => {
    for (const provider of PAYMENT_PROVIDER_PLACEHOLDERS) {
      for (const forbidden of [
        'apiKey',
        'secret',
        'password',
        'terminalKey',
        'shopId',
        'checkoutUrl',
      ]) {
        expect(Object.keys(provider)).not.toContain(forbidden)
      }
    }
  })
})
