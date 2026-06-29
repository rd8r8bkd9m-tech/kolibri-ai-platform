import { AppHeader } from "./AppHeader"
import { ChatWorkspace } from "./chat/ChatWorkspace"
import { LivingKolibri } from "./LivingKolibri"
import { formatClusterSignal } from "../lib/factoryStatus"

const workflowSteps = [
  { label: "Чат", text: "Формулируете задачу по смете, КП или договору." },
  { label: "Фабрика", text: "Kolibri собирает контекст, документы и расчеты." },
  { label: "Контрол", text: "Документы, поиск, биллинг и статус остаются рядом." },
  { label: "Результат", text: "Получаете черновик, файл или следующий точный шаг." },
]

const capabilityItems = [
  "Сметы и материалы",
  "КП и договоры",
  "Поиск по базе",
  "PWA на рабочем столе",
]

const birdSignals = {
  offline: "ожидает соединение",
  thinking: "думает над ответом",
  listening: "слушает ввод",
  idle: "чат готов к работе",
}

function getClusterSignal(clusterStatus) {
  return formatClusterSignal(clusterStatus)
}

export function LandingShell({
  productTitle,
  birdState,
  clusterStatus,
  providers,
  selectedProvider,
  onProviderChange,
  onOpenSettings,
  onOpenApp,
  onOpenControl,
  pwaStatus,
  chatProps,
}) {
  return (
    <main className="landing-main">
      <section className="landing-hero" aria-labelledby="landing-title">
        <nav className="landing-nav" aria-label="Kolibri AI">
          <button className="landing-brand" type="button" onClick={onOpenApp}>
            <LivingKolibri state={birdState} size={38} className="landing-brand-bird" />
            <span>Kolibri AI</span>
          </button>
          <div className="landing-nav-links">
            <a href="#workflow">Процесс</a>
            <a href="#capabilities">Возможности</a>
            <button type="button" onClick={() => onOpenControl("billing")}>Тарифы</button>
          </div>
          <button className="landing-nav-cta" type="button" onClick={onOpenApp}>
            Открыть приложение
          </button>
        </nav>

        <div className="landing-hero-grid">
          <div className="landing-copy">
            <div className="landing-kicker">Chat-first SPA/PWA для прикладной работы</div>
            <h1 id="landing-title">Kolibri AI</h1>
            <p className="landing-lead">
              Чат собирает сметы, КП и документы, а Контрол держит поиск, оплату и
              состояние фабрики в одном спокойном рабочем слое.
            </p>
            <div className="landing-actions">
              <button className="landing-btn landing-btn--primary" type="button" onClick={onOpenApp}>
                Начать в Kolibri
              </button>
              <a className="landing-btn landing-btn--secondary" href="#workflow">
                Посмотреть возможности
              </a>
            </div>
            <dl className="landing-signals" aria-label="Состояние продукта">
              <div>
                <dt>Фабрика</dt>
                <dd>{getClusterSignal(clusterStatus)}</dd>
              </div>
              <div>
                <dt>PWA</dt>
                <dd>{pwaStatus}</dd>
              </div>
              <div>
                <dt>Control</dt>
                <dd>документы · поиск · биллинг</dd>
              </div>
            </dl>
          </div>

          <div className="landing-product" aria-label="Рабочий интерфейс Kolibri AI">
            <div className="landing-bird-dock">
              <LivingKolibri state={birdState} size={64} personality="business" />
              <div>
                <span>Статус</span>
                <strong>{birdSignals[birdState] || "держит рабочий ритм"}</strong>
              </div>
            </div>
            <div className="landing-workbench">
              <AppHeader
                productTitle={productTitle}
                birdState={birdState}
                clusterStatus={clusterStatus}
                providers={providers}
                selectedProvider={selectedProvider}
                onProviderChange={onProviderChange}
                onOpenSettings={onOpenSettings}
              />
              <ChatWorkspace {...chatProps} variant="landing" />
            </div>
          </div>
        </div>
      </section>

      <section className="landing-section landing-workflow" id="workflow" aria-labelledby="workflow-title">
        <div className="landing-section-head">
          <span>Рабочий поток</span>
          <h2 id="workflow-title">От сообщения до готового документа</h2>
        </div>
        <div className="landing-step-grid">
          {workflowSteps.map((step, index) => (
            <article className="landing-step" key={step.label}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              <h3>{step.label}</h3>
              <p>{step.text}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="landing-section landing-capabilities" id="capabilities" aria-labelledby="capabilities-title">
        <div className="landing-section-head">
          <span>Ежедневные сценарии</span>
          <h2 id="capabilities-title">Один вход для команды, документов и фабрики</h2>
        </div>
        <div className="landing-capability-row">
          {capabilityItems.map(item => <span key={item}>{item}</span>)}
        </div>
      </section>
    </main>
  )
}
