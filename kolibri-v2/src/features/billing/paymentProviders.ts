export type PaymentProviderId = 'tbank' | 'yookassa' | 'sbp'

export interface PaymentProviderPlaceholder {
  id: PaymentProviderId
  name: string
  description: string
  settlement: string
  status: 'not_connected'
  configurationAvailable: false
}

/**
 * Product-facing placeholders only. Provider credentials and payment actions
 * must be added by a server-owned billing capability before this state changes.
 */
export const PAYMENT_PROVIDER_PLACEHOLDERS: readonly PaymentProviderPlaceholder[] = Object.freeze([
  {
    id: 'tbank',
    name: 'Т-Банк',
    description: 'Интернет-эквайринг для карт и платёжных ссылок.',
    settlement: 'Карты · платёжная ссылка',
    status: 'not_connected',
    configurationAvailable: false,
  },
  {
    id: 'yookassa',
    name: 'ЮKassa',
    description: 'Приём оплаты с фискализацией через подключённую кассу.',
    settlement: 'Карты · электронные способы',
    status: 'not_connected',
    configurationAvailable: false,
  },
  {
    id: 'sbp',
    name: 'СБП QR',
    description: 'Оплата по QR-коду через банк-эквайер организации.',
    settlement: 'QR-код · Система быстрых платежей',
    status: 'not_connected',
    configurationAvailable: false,
  },
])

export function paymentProviderStatus(provider: PaymentProviderPlaceholder): 'Не подключено' {
  if (provider.status !== 'not_connected' || provider.configurationAvailable) {
    throw new Error('Payment provider placeholder cannot advertise an enabled configuration')
  }
  return 'Не подключено'
}
