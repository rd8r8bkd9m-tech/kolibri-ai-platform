import { CreditCard, Landmark, QrCode, ShieldCheck } from 'lucide-react'
import { PAYMENT_PROVIDER_PLACEHOLDERS, paymentProviderStatus, type PaymentProviderId } from './paymentProviders'

const providerIcons: Record<PaymentProviderId, typeof CreditCard> = {
  tbank: Landmark,
  yookassa: CreditCard,
  sbp: QrCode,
}

export default function BillingSettings() {
  return (
    <div className="settings-section" data-billing-placeholder>
      <header className="settings-section-heading">
        <div>
          <p className="settings-kicker">Биллинг</p>
          <h2>Оплата и тариф</h2>
          <p>Платёжный контур подготовлен в интерфейсе, но пока не активирован. Списания не выполняются.</p>
        </div>
        <span className="settings-status-pill is-muted">Бета · без списаний</span>
      </header>

      <section className="settings-plan-row" aria-labelledby="current-plan-title">
        <div>
          <span>Текущий режим</span>
          <strong id="current-plan-title">Закрытая бета</strong>
        </div>
        <p>Тариф и лимиты будут показаны до первого подтверждения оплаты.</p>
      </section>

      <div className="settings-provider-list" aria-label="Платёжные провайдеры">
        {PAYMENT_PROVIDER_PLACEHOLDERS.map(provider => {
          const Icon = providerIcons[provider.id]
          return (
            <article className="settings-provider-row" key={provider.id}>
              <span className="settings-provider-icon" aria-hidden="true"><Icon /></span>
              <div className="settings-provider-copy">
                <div>
                  <h3>{provider.name}</h3>
                  <span className="settings-status-pill is-offline">{paymentProviderStatus(provider)}</span>
                </div>
                <p>{provider.description}</p>
                <small>{provider.settlement}</small>
              </div>
              <button type="button" disabled aria-disabled="true">Настройка недоступна</button>
            </article>
          )
        })}
      </div>

      <aside className="settings-billing-note">
        <ShieldCheck aria-hidden="true" />
        <div>
          <strong>Секреты не вводятся в браузере</strong>
          <p>После подключения серверного биллинга реквизиты провайдера будут храниться на защищённой стороне, а здесь появятся только статус и безопасные действия.</p>
        </div>
      </aside>
    </div>
  )
}
