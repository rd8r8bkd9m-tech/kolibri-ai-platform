import { ArrowRight, CheckCircle2, Copy, RefreshCw, Search } from 'lucide-react'
import { useMemo, useState } from 'react'
import DeveloperFrame from '@/features/developers/DeveloperFrame'
import { liveDeveloperEndpoints } from '@/features/developers/developerCapabilities'
import { useCapabilities } from '@/features/capabilities'
import { useLocale } from '@/features/localization'

const ENDPOINT_COPY: Record<string, { title: string; description: string }> = {
  '/v1/models': { title: 'Список моделей', description: 'Возвращает публичную модель kolibri, доступную текущему API-ключу.' },
  '/v1/responses': { title: 'Responses API', description: 'Создаёт типизированный ответ модели с поддержкой streaming и фонового режима.' },
  '/v1/chat/completions': { title: 'Chat Completions', description: 'Совместимый маршрут для существующих OpenAI SDK и chat-интеграций.' },
  '/v1/realtime/sessions': { title: 'Realtime sessions', description: 'Создаёт сессию потокового голосового взаимодействия.' },
}

const QUICKSTARTS = {
  javascript: `import OpenAI from "openai";

const client = new OpenAI({
  baseURL: "https://kolibriai.ru/v1",
  apiKey: process.env.KOLIBRI_API_KEY,
});

const response = await client.responses.create({
  model: "kolibri",
  input: "Составь смету на штукатурку 420 м²",
});

console.log(response.output_text);`,
  python: `import os
from openai import OpenAI

client = OpenAI(
    base_url="https://kolibriai.ru/v1",
    api_key=os.environ["KOLIBRI_API_KEY"],
)

response = client.responses.create(
    model="kolibri",
    input="Составь смету на штукатурку 420 м²",
)

print(response.output_text)`,
  curl: `curl https://kolibriai.ru/v1/responses \\
  -H "Authorization: Bearer $KOLIBRI_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "kolibri",
    "input": "Составь предварительную смету на штукатурку 420 м² в Казани"
  }'`,
}

type QuickstartLanguage = keyof typeof QUICKSTARTS

export default function DeveloperDocsPage() {
  const { t } = useLocale()
  const { catalog, loading, refresh } = useCapabilities()
  const endpoints = liveDeveloperEndpoints(catalog)
  const [query, setQuery] = useState('')
  const [copied, setCopied] = useState(false)
  const [language, setLanguage] = useState<QuickstartLanguage>('javascript')
  const quickstart = QUICKSTARTS[language]

  const filteredEndpoints = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase()
    if (!normalizedQuery) return endpoints
    return endpoints.filter(endpoint => {
      const copy = ENDPOINT_COPY[endpoint.path]
      return `${endpoint.method} ${endpoint.path} ${copy?.title ?? ''} ${copy?.description ?? ''}`.toLowerCase().includes(normalizedQuery)
    })
  }, [endpoints, query])

  const copyQuickstart = async () => {
    await navigator.clipboard.writeText(quickstart)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1800)
  }

  return (
    <DeveloperFrame title="API Platform" copy="Создавайте продукты на модели kolibri через знакомые SDK. Здесь собраны быстрый старт, живые контракты и правила работы в production.">
      <nav className="developer-api-section-nav" aria-label="Разделы API Platform">
        <a href="#quickstart" className="is-active">Обзор</a>
        <a href="#endpoints">Модели</a>
        <a href="#responses">Агенты</a>
        <a href="#endpoints">Инструменты</a>
        <a href="#errors">Production</a>
        <a href="#endpoints">API reference</a>
      </nav>

      <div className="developer-docs-layout">
        <aside className="developer-docs-sidebar" aria-label="Разделы документации">
          <a href="#quickstart" className="is-active">Главная</a>
          <strong>Начало работы</strong>
          <a href="#quickstart">Быстрый старт</a>
          <a href="#authentication">Авторизация</a>
          <strong>Основные концепции</strong>
          <a href="#responses">Responses API</a>
          <a href="#responses">Фоновые задачи</a>
          <a href="#responses">Streaming</a>
          <strong>Справочник</strong>
          <a href="#endpoints">Endpoints</a>
          <a href="#errors">Ошибки</a>
        </aside>

        <div className="developer-docs-content">
          <section id="quickstart" className="developer-docs-section" aria-labelledby="quickstart-title">
            <div className="developer-docs-lead">
              <div>
                <p className="developer-section-label">Developer quickstart</p>
                <h2 id="quickstart-title">Первый ответ за несколько минут</h2>
                <p>Установите официальный OpenAI SDK, укажите адрес Kolibri и вызовите публичную модель <code>kolibri</code>.</p>
                <div className="developer-docs-actions">
                  <a href="#authentication">Начать <ArrowRight aria-hidden="true" /></a>
                  <a href="#endpoints">Создать API-ключ</a>
                </div>
              </div>
              <div className="developer-docs-release">
                <span className={endpoints.length ? 'is-live' : ''}><i /> {loading ? 'Проверяем API' : endpoints.length ? 'API доступен' : 'Статус API не подтверждён'}</span>
                <small>Модель: <code>kolibri</code></small>
              </div>
            </div>

            <div className="developer-code-card is-docs">
              <div className="developer-code-toolbar">
                <div className="developer-code-tabs" role="tablist" aria-label="Язык примера">
                  {(Object.keys(QUICKSTARTS) as QuickstartLanguage[]).map(item => (
                    <button
                      key={item}
                      type="button"
                      role="tab"
                      aria-selected={language === item}
                      className={language === item ? 'is-active' : undefined}
                      onClick={() => setLanguage(item)}
                    >
                      {item === 'javascript' ? 'JavaScript' : item === 'python' ? 'Python' : 'cURL'}
                    </button>
                  ))}
                </div>
                <button type="button" onClick={() => void copyQuickstart()} aria-label="Скопировать пример запроса">
                  <Copy aria-hidden="true" /> {copied ? 'Скопировано' : 'Копировать'}
                </button>
              </div>
              <pre><code>{quickstart}</code></pre>
            </div>
          </section>

          <section id="authentication" className="developer-docs-section" aria-labelledby="auth-title">
            <p className="developer-section-label">Безопасность</p>
            <h2 id="auth-title">Авторизация</h2>
            <p>Передавайте ключ в каждом запросе: <code>Authorization: Bearer $KOLIBRI_API_KEY</code>. Не размещайте секрет в браузерном коде и публичных репозиториях.</p>
            <div className="developer-callout">
              <strong>Ключи принадлежат организации.</strong>
              <span>Создавайте отдельный ключ для каждого сервиса и отзывайте его сразу после утечки или завершения интеграции.</span>
            </div>
          </section>

          <section id="endpoints" className="developer-docs-section" aria-labelledby="developer-endpoints-title">
            <div className="developer-docs-titlebar">
              <div>
                <p className="developer-section-label">Текущий релиз</p>
                <h2 id="developer-endpoints-title">{t('developer.liveEndpoints')}</h2>
                <p>{loading ? 'Проверяем capability registry…' : endpoints.length ? 'Показаны только маршруты, для которых backend предоставил живое доказательство.' : 'Живое доказательство маршрутов сейчас недоступно.'}</p>
              </div>
              <button type="button" onClick={() => void refresh()} disabled={loading}><RefreshCw aria-hidden="true" />{loading ? 'Проверяем…' : 'Проверить снова'}</button>
            </div>

            {endpoints.length > 0 && (
              <label className="developer-docs-search">
                <Search aria-hidden="true" />
                <span className="sr-only">Найти endpoint</span>
                <input value={query} onChange={event => setQuery(event.target.value)} placeholder="Найти endpoint" type="search" />
              </label>
            )}

            {filteredEndpoints.length > 0 ? (
              <div className="developer-endpoint-list">
                {filteredEndpoints.map(endpoint => {
                  const copy = ENDPOINT_COPY[endpoint.path]
                  return (
                    <article key={endpoint.path} className="developer-endpoint-row">
                      <span>{endpoint.method}</span>
                      <div>
                        <code>{endpoint.path}</code>
                        <h3>{copy?.title ?? endpoint.path}</h3>
                        <p>{copy?.description}</p>
                      </div>
                      <span className="developer-endpoint-live"><CheckCircle2 aria-hidden="true" /> доступен</span>
                    </article>
                  )
                })}
              </div>
            ) : endpoints.length > 0 ? (
              <p className="developer-empty-state">По этому запросу ничего не найдено.</p>
            ) : !loading ? (
              <div className="developer-empty-state">
                <strong>Справочник доступен, но живой статус API сейчас не подтверждён.</strong>
                <span>Kolibri не показывает неподтверждённые маршруты как рабочие. Проверьте соединение ещё раз — руководства и контракты ниже остаются доступными.</span>
              </div>
            ) : null}
          </section>

          <section id="responses" className="developer-docs-section" aria-labelledby="responses-title">
            <p className="developer-section-label">Основной контракт</p>
            <h2 id="responses-title">Responses API</h2>
            <p>Передайте строку или типизированный массив входных элементов в поле <code>input</code>. Для потокового ответа укажите <code>stream: true</code>; для длительной задачи — <code>background: true</code>.</p>
            <div className="developer-concept-grid">
              <article><strong>Обычный ответ</strong><span>Получите готовый результат одним HTTP-запросом.</span></article>
              <article><strong>Streaming</strong><span>Показывайте текст и события по мере выполнения.</span></article>
              <article><strong>Background</strong><span>Запускайте длительную работу и забирайте результат позже.</span></article>
            </div>
          </section>

          <section id="errors" className="developer-docs-section" aria-labelledby="errors-title">
            <p className="developer-section-label">Диагностика</p>
            <h2 id="errors-title">Ошибки не маскируются успехом</h2>
            <p>Клиент должен показать ошибку и не сохранять ответ как готовый результат, если запрос завершился неуспешно.</p>
            <div className="developer-error-grid">
              <article><code>400</code><span>Проверьте тело запроса и обязательные поля.</span></article>
              <article><code>401</code><span>Передайте действующий ключ организации.</span></article>
              <article><code>429</code><span>Повторите запрос с экспоненциальной задержкой.</span></article>
              <article><code>503</code><span>Маршрут временно недоступен; ответ не считается готовым.</span></article>
            </div>
          </section>
        </div>

        <aside className="developer-docs-toc" aria-label="На этой странице">
          <strong>На этой странице</strong>
          <a href="#quickstart">Быстрый старт</a>
          <a href="#authentication">Авторизация</a>
          <a href="#endpoints">Endpoints</a>
          <a href="#responses">Responses API</a>
          <a href="#errors">Ошибки</a>
        </aside>
      </div>
    </DeveloperFrame>
  )
}
