export function BillingPanel({ plansState, form, setForm, loading, message, onSubmit }) {
  const plans = plansState?.plans || []
  return (
    <div className="control-section">
      <div className="control-section-head">
        <h3>Подписки</h3>
        <span className={`control-pill ${plansState?.configured ? "ready" : ""}`}>Т-Банк</span>
      </div>
      <div className="billing-grid">
        {plans.map(plan => (
          <button
            key={plan.id}
            className={`plan-card ${form.plan_id === plan.id ? "selected" : ""}`}
            onClick={() => setForm(prev => ({ ...prev, plan_id: plan.id }))}
            type="button"
          >
            <div className="plan-card-top">
              <strong>{plan.name}</strong>
              <span>{plan.price_rub} ₽/мес</span>
            </div>
            <div className="plan-meta">{plan.primary_use}</div>
            <div className="plan-limit">{plan.monthly_limit}</div>
            <div className="plan-tags">
              {plan.highlights.map(item => <span key={item}>{item}</span>)}
            </div>
          </button>
        ))}
      </div>
      <form className="checkout-form" onSubmit={onSubmit}>
        <label className="field">
          <span>Email</span>
          <input value={form.email} onChange={e => setForm(prev => ({ ...prev, email: e.target.value }))} type="email" required placeholder="client@company.ru" />
        </label>
        <div className="form-grid">
          <label className="field">
            <span>Имя</span>
            <input value={form.name} onChange={e => setForm(prev => ({ ...prev, name: e.target.value }))} placeholder="Алексей" />
          </label>
          <label className="field">
            <span>Телефон</span>
            <input value={form.phone} onChange={e => setForm(prev => ({ ...prev, phone: e.target.value }))} placeholder="+7..." />
          </label>
        </div>
        <label className="field">
          <span>Компания</span>
          <input value={form.company} onChange={e => setForm(prev => ({ ...prev, company: e.target.value }))} placeholder="Ремонтная компания" />
        </label>
        {message && <div className="billing-message">{message}</div>}
        <button className="primary-action" disabled={loading || !form.email.trim()}>
          {loading ? "Подключаю..." : plansState?.configured ? "Оплатить через Т-Банк" : "Сохранить заявку"}
        </button>
      </form>
    </div>
  )
}
