import {
  Activity,
  ArrowRight,
  BookOpen,
  Boxes,
  Check,
  Copy,
  FileStack,
  FlaskConical,
  KeyRound,
  Radio,
  Workflow,
} from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'
import DeveloperFrame from '@/features/developers/DeveloperFrame'
import ApiKeyPanel from '@/features/developers/ApiKeyPanel'
import { isDeveloperSurfaceLive, liveDeveloperEndpoints } from '@/features/developers/developerCapabilities'
import { useCapabilities } from '@/features/capabilities'
import { useLocale } from '@/features/localization'
import type { AuthUser } from '@/lib/api'

export default function DevelopersPage({ user }: { user: AuthUser | null }) {
  const { t } = useLocale()
  const { catalog, loading } = useCapabilities()
  const keyManagementLive = isDeveloperSurfaceLive(catalog, 'apiKeys')
  const endpoints = liveDeveloperEndpoints(catalog)
  const [copied, setCopied] = useState(false)
  const quickstart = `curl https://kolibriai.ru/v1/responses \\
  -H "Authorization: Bearer $KOLIBRI_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"model":"kolibri","input":"Составь смету"}'`

  const copyQuickstart = async () => {
    await navigator.clipboard.writeText(quickstart)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1800)
  }

  return (
    <DeveloperFrame title={t('developer.title')} copy={t('developer.copy')}>
      <section className="developer-overview-status" aria-label="Текущая конфигурация API Platform">
        <div>
          <span>Публичная модель</span>
          <strong><code>kolibri</code></strong>
        </div>
        <div>
          <span>Живые endpoints</span>
          <strong>{loading ? 'Проверяем…' : endpoints.length}</strong>
        </div>
        <div>
          <span>Основной контракт</span>
          <strong>Responses API</strong>
        </div>
        <div>
          <span>Состояние</span>
          <strong className={endpoints.length ? 'is-live' : undefined}>
            <i /> {loading ? 'Проверка' : endpoints.length ? 'API доступен' : 'Нет доказательства'}
          </strong>
        </div>
      </section>

      <section className="developer-platform-grid" aria-label="Возможности платформы">
        <article>
          <Radio aria-hidden="true" />
          <div><h2>API Platform</h2><p>OpenAI-совместимый Responses API, потоковые ответы и фоновые задачи.</p></div>
          <span className={`developer-live-status ${endpoints.length ? 'is-live' : ''}`}>
            <i /> {loading ? 'Проверяем' : endpoints.length ? 'Работает' : 'Нет подтверждения'}
          </span>
        </article>
        <Link to="/docs">
          <BookOpen aria-hidden="true" />
          <div><h2>Документация</h2><p>Quickstart, авторизация и контракты только для доступных маршрутов.</p></div>
          <span>Читать документацию <ArrowRight aria-hidden="true" /></span>
        </Link>
        <Link to="/playground">
          <FlaskConical aria-hidden="true" />
          <div><h2>Playground</h2><p>Проверяйте модель kolibri в браузере до интеграции в свой продукт.</p></div>
          <span>Открыть Playground <ArrowRight aria-hidden="true" /></span>
        </Link>
      </section>

      <section className="developer-build" aria-labelledby="developer-build-title">
        <div className="developer-build-heading">
          <div>
            <p className="developer-section-label">Стройте на Kolibri</p>
            <h2 id="developer-build-title">От первого вызова до управляемого AI-продукта</h2>
          </div>
          <Link to="/docs">Все руководства <ArrowRight aria-hidden="true" /></Link>
        </div>
        <div className="developer-build-grid">
          <Link to="/docs#responses">
            <Activity aria-hidden="true" />
            <span>Responses API</span>
            <strong>Текст, streaming и фоновые ответы через единый контракт.</strong>
            <em>{endpoints.some(endpoint => endpoint.path === '/v1/responses') ? 'Доступно сейчас' : 'Проверяется'}</em>
          </Link>
          <Link to="/playground">
            <Workflow aria-hidden="true" />
            <span>Flows и агенты</span>
            <strong>Проверяйте промпты и сценарии до подключения к продукту.</strong>
            <em>Открыть Playground</em>
          </Link>
          <Link to="/app">
            <FileStack aria-hidden="true" />
            <span>Файлы и документы</span>
            <strong>Передавайте исходные материалы и получайте сохраняемый результат.</strong>
            <em>Открыть Workspace</em>
          </Link>
          <Link to="/control">
            <Boxes aria-hidden="true" />
            <span>AI Factory</span>
            <strong>Задачи, исполнители, маршрутизация и доказательства выполнения.</strong>
            <em>Перейти в Control Center</em>
          </Link>
        </div>
      </section>

      <section className="developer-quickstart" aria-labelledby="developer-quickstart-title">
        <div className="developer-quickstart-copy">
          <p className="developer-section-label">Быстрый старт</p>
          <h2 id="developer-quickstart-title">Первый ответ за несколько минут</h2>
          <p>Вызовите публичную модель <code>kolibri</code> через совместимый Responses API. Ключ передаётся только в заголовке Authorization.</p>
          <Link to="/docs">Открыть руководство <ArrowRight aria-hidden="true" /></Link>
          <ol className="developer-quickstart-steps">
            <li><span>1</span><div><strong>Создайте ключ</strong><small>Отдельный для каждого сервиса</small></div></li>
            <li><span>2</span><div><strong>Укажите base URL</strong><small>https://kolibriai.ru/v1</small></div></li>
            <li><span>3</span><div><strong>Вызовите kolibri</strong><small>Через официальный OpenAI SDK</small></div></li>
          </ol>
        </div>
        <div className="developer-code-card">
          <div className="developer-code-toolbar">
            <span>cURL</span>
            <button type="button" onClick={() => void copyQuickstart()} aria-label="Скопировать пример cURL">
              {copied ? <Check aria-hidden="true" /> : <Copy aria-hidden="true" />}
              {copied ? 'Скопировано' : 'Копировать'}
            </button>
          </div>
          <pre><code>{quickstart}</code></pre>
        </div>
      </section>

      <div className="developer-card-grid">
        <Link to="/docs" className="developer-card">
          <BookOpen aria-hidden="true" />
          <div>
            <h2>{t('developer.docs')}</h2>
            <p>{t('developer.docsCopy')}</p>
          </div>
          <span>{t('developer.openDocs')} <ArrowRight aria-hidden="true" /></span>
        </Link>
        <Link to="/playground" className="developer-card">
          <FlaskConical aria-hidden="true" />
          <div>
            <h2>{t('developer.playground')}</h2>
            <p>{t('developer.playgroundCopy')}</p>
          </div>
          <span>{t('developer.openPlayground')} <ArrowRight aria-hidden="true" /></span>
        </Link>
        <Link to={user ? '/settings' : '/login'} className="developer-card">
          <KeyRound aria-hidden="true" />
          <div>
            <h2>API-ключи</h2>
            <p>Создавайте и отзывайте ключи. Секрет показывается один раз и не попадает в журнал интерфейса.</p>
          </div>
          <span>{user ? 'Перейти в настройки' : 'Войти для управления'} <ArrowRight aria-hidden="true" /></span>
        </Link>
      </div>

      {keyManagementLive && <ApiKeyPanel user={user} />}
    </DeveloperFrame>
  )
}
