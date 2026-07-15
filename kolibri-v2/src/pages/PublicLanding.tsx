import { useState, type FormEvent } from 'react'
import { ArrowRight, CheckCircle2, FileText, MessageSquareText } from 'lucide-react'
import { Link, useNavigate } from 'react-router'
import { useLocale } from '@/features/localization'
import PublicPortalFrame from '@/features/portal/PublicPortalFrame'

export default function PublicLanding() {
  const { t } = useLocale()
  const navigate = useNavigate()
  const [prompt, setPrompt] = useState('')

  const start = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const value = prompt.trim()
    navigate(value ? `/app?q=${encodeURIComponent(value)}` : '/app')
  }

  return (
    <PublicPortalFrame>
        <section className="public-hero" aria-labelledby="landing-title">
          <p className="public-hero-eyebrow">Kolibri AI OS</p>
          <h1 id="landing-title">{t('landing.title')}</h1>
          <p className="public-hero-copy">{t('landing.copy')}</p>

          <form className="public-prompt" onSubmit={start}>
            <label className="sr-only" htmlFor="landing-prompt">{t('landing.promptLabel')}</label>
            <input
              id="landing-prompt"
              value={prompt}
              onChange={event => setPrompt(event.target.value)}
              placeholder={t('landing.promptPlaceholder')}
              autoComplete="off"
            />
            <button type="submit" aria-label={t('landing.start')}>
              <span>{t('landing.start')}</span>
              <ArrowRight size={20} aria-hidden="true" />
            </button>
          </form>
          <p className="public-prompt-note">{t('landing.promptNote')}</p>
          <a className="public-secondary-action" href="#how">
            Как это работает <ArrowRight size={17} aria-hidden="true" />
          </a>
        </section>

        <section className="public-product" id="product" aria-labelledby="product-title">
          <div className="public-product-heading">
            <p>{t('landing.productEyebrow')}</p>
            <h2 id="product-title">{t('landing.productTitle')}</h2>
          </div>
          <div className="public-product-grid">
            <article>
              <MessageSquareText aria-hidden="true" />
              <h3>{t('landing.projectTitle')}</h3>
              <p>{t('landing.projectCopy')}</p>
            </article>
            <article>
              <FileText aria-hidden="true" />
              <h3>{t('landing.artifactTitle')}</h3>
              <p>{t('landing.artifactCopy')}</p>
            </article>
            <article>
              <CheckCircle2 aria-hidden="true" />
              <h3>{t('landing.verifyTitle')}</h3>
              <p>{t('landing.verifyCopy')}</p>
            </article>
          </div>
        </section>

        <section className="public-how" id="how" aria-labelledby="public-how-title">
          <div className="public-product-heading">
            <p>Как работает</p>
            <h2 id="public-how-title">Один понятный путь внутри проекта</h2>
          </div>
          <ol>
            <li><span>1</span><div><h3>Опишите результат</h3><p>Начните обычной фразой или продолжите сохранённый проект.</p></div></li>
            <li><span>2</span><div><h3>Следите за ходом работы</h3><p>Kolibri показывает реальные этапы, источники и запросы на уточнение.</p></div></li>
            <li><span>3</span><div><h3>Получите сохраняемый результат</h3><p>Готовые материалы остаются в проекте и открываются после перезагрузки.</p></div></li>
          </ol>
        </section>

        <section className="public-trust" aria-labelledby="public-trust-title">
          <div>
            <p className="public-hero-eyebrow">Контроль</p>
            <h2 id="public-trust-title">Только готовые к работе возможности</h2>
            <p>Неподтверждённый инструмент не появляется в интерфейсе, а созданный файл проходит проверку байтов и повторного открытия.</p>
          </div>
          <Link className="public-secondary-link" to="/security">Как устроена безопасность <ArrowRight aria-hidden="true" /></Link>
        </section>

        <section className="public-final-cta" aria-labelledby="public-final-title">
          <div>
            <p className="public-hero-eyebrow">Kolibri AI</p>
            <h2 id="public-final-title">Начните с одной задачи</h2>
            <p>Новый проект откроется в защищённом рабочем пространстве.</p>
          </div>
          <Link className="public-primary-link" to="/app">
            Открыть Kolibri <ArrowRight aria-hidden="true" />
          </Link>
        </section>
    </PublicPortalFrame>
  )
}
