import { ArrowRight, Check } from 'lucide-react'
import { Link } from 'react-router'
import PublicPortalFrame from '@/features/portal/PublicPortalFrame'

export type PublicInfoPageKind = 'pricing' | 'security' | 'privacy' | 'terms'

interface PublicInfoPageProps {
  kind: PublicInfoPageKind
}

interface PageSection {
  title: string
  paragraphs?: string[]
  bullets?: string[]
}

const content: Record<Exclude<PublicInfoPageKind, 'pricing'>, {
  eyebrow: string
  title: string
  lead: string
  sections: PageSection[]
}> = {
  security: {
    eyebrow: 'Безопасность',
    title: 'Доступ определяется сессией, а результат — проверкой',
    lead: 'Kolibri отделяет публичный портал от рабочего пространства и не выдаёт неподтверждённую возможность за работающую.',
    sections: [
      {
        title: 'Сессии и проекты',
        bullets: [
          'Рабочие маршруты получают noindex и открываются через серверную сессию.',
          'Доступ к проекту, файлу и артефакту проверяется в пределах выданной сессии.',
          'Публичная страница не загружает историю, документы или названия проектов.',
        ],
      },
      {
        title: 'Инструменты и секреты',
        bullets: [
          'Ключи провайдеров остаются на сервере и не попадают в клиентскую сборку.',
          'Инструмент показывается только после проверки доступного маршрута и готового отображения результата.',
          'В публичном интерфейсе не раскрываются внутренняя топология, служебные prompts и приватные рассуждения модели.',
        ],
      },
      {
        title: 'Артефакты и проверки',
        bullets: [
          'Файл считается готовым после получения байтов, MIME-типа, размера и SHA-256.',
          'Смета не получает статус «проверено» без достаточных данных и источников.',
          'Статус доступности относится к текущему release и может честно быть degraded или unavailable.',
        ],
      },
      {
        title: 'Границы заявления',
        paragraphs: [
          'Страница описывает технические меры текущего продукта и не заявляет внешнюю сертификацию, которой нет. Для критичных данных пользователь видит источники и статус проверки до утверждения результата.',
        ],
      },
    ],
  },
  privacy: {
    eyebrow: 'Конфиденциальность',
    title: 'Данные используются для выполнения вашей задачи',
    lead: 'Редакция от 15 июля 2026 года. Эта политика относится к бета-версии Kolibri AI на kolibriai.ru.',
    sections: [
      {
        title: 'Какие данные обрабатываются',
        bullets: [
          'Данные аккаунта, которые пользователь вводит при регистрации.',
          'Сообщения, файлы, проекты и артефакты, которые пользователь создаёт или загружает.',
          'Технические события сессии, ошибки, release ID и сведения, необходимые для безопасности сервиса.',
        ],
      },
      {
        title: 'Зачем они нужны',
        bullets: [
          'Чтобы сохранить контекст проекта и вернуть результат после перезагрузки.',
          'Чтобы вызвать выбранный пользователем инструмент и сохранить полученный артефакт.',
          'Чтобы предотвращать злоупотребления, диагностировать ошибки и восстанавливать работу сервиса.',
        ],
      },
      {
        title: 'Передача обработчикам',
        paragraphs: [
          'Часть запроса может быть передана подключённому AI- или инструментальному провайдеру только для выполнения выбранного действия. Kolibri не продаёт содержимое проектов для рекламного таргетинга.',
        ],
      },
      {
        title: 'Управление данными',
        paragraphs: [
          'Пользователь может удалять проекты в интерфейсе, отзывать созданные API-ключи и завершать работу с аккаунтом. Сроки технического удаления и резервного хранения применяются с учётом безопасности и обязательных требований закона.',
        ],
      },
    ],
  },
  terms: {
    eyebrow: 'Условия использования',
    title: 'Понятные правила для бета-версии',
    lead: 'Редакция от 15 июля 2026 года. Используя Kolibri AI, пользователь соглашается с этими условиями.',
    sections: [
      {
        title: 'Назначение сервиса',
        paragraphs: [
          'Kolibri помогает вести задачу от диалога до сохраняемого результата. Фактический набор возможностей определяется текущим release и доступностью подтверждённых маршрутов.',
        ],
      },
      {
        title: 'Ответственность пользователя',
        bullets: [
          'Не загружать данные и материалы без законного основания.',
          'Не использовать сервис для нарушения закона, прав третьих лиц или безопасности систем.',
          'Проверять критичные сведения, договорные условия и финансовые решения до внешнего применения.',
        ],
      },
      {
        title: 'Результаты AI',
        paragraphs: [
          'Kolibri показывает источники и проверки там, где они доступны, но результат AI может потребовать профессионального подтверждения. Сервис не имитирует созданный файл или выполненное действие: недоступный маршрут должен быть обозначен явно.',
        ],
      },
      {
        title: 'Оплата и изменения',
        paragraphs: [
          'До активации платёжного контура списания не выполняются. После его включения цена, лимиты и период оплаты показываются до подтверждения. Существенные изменения условий публикуются на этой странице с новой датой редакции.',
        ],
      },
    ],
  },
}

const plans = [
  { name: 'Free', price: '0 ₽', note: 'Для знакомства', features: ['1 пользователь', 'До 2 полных AI-генераций', 'До 3 сохранённых смет', 'PDF с отметкой Free'] },
  { name: 'Founders', price: '1 490 ₽', note: 'в месяц · первые 30 компаний', features: ['1 пользователь', '20 AI-генераций в месяц', 'До 60 смет', 'PDF и XLSX', 'Импорт прайсов'] },
  { name: 'Pro', price: '2 490 ₽', note: 'в месяц', features: ['1 пользователь', '20 AI-генераций в месяц', 'До 60 смет', 'Каталоги и версии', 'Экспорт без водяного знака'] },
  { name: 'Team', price: '6 990 ₽', note: 'в месяц', features: ['До 5 пользователей', '80 AI-генераций в месяц', 'До 250 смет', 'Общая библиотека и роли', 'Приоритетная поддержка'] },
]

function PricingPage() {
  return (
    <PublicPortalFrame>
      <section className="public-info-hero" aria-labelledby="public-info-title">
        <p className="public-hero-eyebrow">Тарифы</p>
        <h1 id="public-info-title">Прозрачные условия платной беты</h1>
        <p>До включения платёжного контура списаний нет. После активации выбранный тариф, лимиты и итоговая сумма будут показаны до подтверждения.</p>
      </section>

      <section className="public-pricing" aria-label="Тарифы Kolibri AI">
        <div className="public-plan-grid">
          {plans.map(plan => (
            <article key={plan.name} className={plan.name === 'Founders' ? 'is-featured' : undefined}>
              <p className="public-plan-name">{plan.name}</p>
              <p className="public-plan-price">{plan.price}</p>
              <p className="public-plan-note">{plan.note}</p>
              <ul>
                {plan.features.map(feature => <li key={feature}><Check aria-hidden="true" />{feature}</li>)}
              </ul>
              <Link className="public-plan-action" to="/app">Открыть Kolibri <ArrowRight aria-hidden="true" /></Link>
            </article>
          ))}
        </div>
        <p className="public-pricing-disclaimer">Годовая скидка 20% и дополнительный пакет 20 AI-генераций за 990 ₽ применяются после включения биллинга. Enterprise — от 25 000 ₽ по отдельному договору.</p>
      </section>
    </PublicPortalFrame>
  )
}

export default function PublicInfoPage({ kind }: PublicInfoPageProps) {
  if (kind === 'pricing') return <PricingPage />
  const page = content[kind]

  return (
    <PublicPortalFrame>
      <section className="public-info-hero" aria-labelledby="public-info-title">
        <p className="public-hero-eyebrow">{page.eyebrow}</p>
        <h1 id="public-info-title">{page.title}</h1>
        <p>{page.lead}</p>
      </section>
      <div className="public-info-sections">
        {page.sections.map(section => (
          <section key={section.title}>
            <h2>{section.title}</h2>
            {section.paragraphs?.map(paragraph => <p key={paragraph}>{paragraph}</p>)}
            {section.bullets ? (
              <ul>
                {section.bullets.map(bullet => <li key={bullet}>{bullet}</li>)}
              </ul>
            ) : null}
          </section>
        ))}
        <aside className="public-info-cta">
          <div>
            <h2>Перейти к работе</h2>
            <p>Создайте новый проект или продолжите сохранённую задачу в Kolibri.</p>
          </div>
          <Link className="public-primary-link" to="/app">Открыть Kolibri <ArrowRight aria-hidden="true" /></Link>
        </aside>
      </div>
    </PublicPortalFrame>
  )
}
