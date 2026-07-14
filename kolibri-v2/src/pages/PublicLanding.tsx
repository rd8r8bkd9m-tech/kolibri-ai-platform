import { useState, type FormEvent } from 'react'
import { ArrowRight, CheckCircle2, FileText, MessageSquareText } from 'lucide-react'
import { Link, useNavigate } from 'react-router'
import CartoonMascot from '@/components/CartoonMascot'
import { useLocale } from '@/features/localization'

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
    <div className="public-landing">
      <header className="public-landing-header">
        <Link className="public-brand" to="/" aria-label="Kolibri">
          <CartoonMascot size={38} />
          <span>Kolibri</span>
        </Link>
        <nav className="public-navigation" aria-label={t('landing.navigation')}>
          <a href="#product">{t('landing.product')}</a>
          <Link to="/developers">{t('landing.developers')}</Link>
          <Link to="/docs">{t('landing.docs')}</Link>
        </nav>
        <div className="public-header-actions">
          <Link className="public-text-link" to="/login">{t('landing.signIn')}</Link>
          <Link className="public-primary-link" to="/app">{t('landing.open')}</Link>
        </div>
      </header>

      <main>
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
      </main>

      <footer className="public-footer">
        <span>© 2026 Kolibri AI</span>
        <div>
          <Link to="/docs">{t('landing.docs')}</Link>
          <Link to="/developers">API</Link>
        </div>
      </footer>
    </div>
  )
}
