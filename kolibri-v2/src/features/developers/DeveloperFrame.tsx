import type { ReactNode } from 'react'
import { ArrowUpRight, Search } from 'lucide-react'
import { Link, NavLink, useLocation } from 'react-router'
import CartoonMascot from '@/components/CartoonMascot'
import { useLocale } from '@/features/localization'

interface DeveloperFrameProps {
  title: string
  copy: string
  children: ReactNode
}

const navigation = [
  { to: '/developers', label: 'developer.overview', end: true },
  { to: '/docs', label: 'developer.docs', end: false },
  { to: '/playground', label: 'developer.playground', end: false },
] as const

const platformNavigation = [
  { to: '/developers', label: 'Обзор' },
  { to: '/docs', label: 'API' },
  { to: '/docs#endpoints', label: 'API reference' },
  { to: '/control', label: 'Фабрика' },
]

export default function DeveloperFrame({ title, copy, children }: DeveloperFrameProps) {
  const { t } = useLocale()
  const { pathname } = useLocation()
  const overview = pathname === '/developers'

  return (
    <div className="developer-portal">
      <a className="developer-skip-link" href="#developer-main">Перейти к содержанию</a>
      <header className="developer-topbar">
        <Link className="developer-brand" to="/developers" aria-label="Kolibri Developers — главная">
          <CartoonMascot size={30} />
          <span>Kolibri</span>
          <em>Developers</em>
        </Link>
        <nav className="developer-global-nav" aria-label={t('developer.eyebrow')}>
          {platformNavigation.map(item => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/developers'}
              className={({ isActive }) => isActive ? 'is-active' : undefined}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="developer-topbar-actions">
          <Link className="developer-search-link" to="/docs" aria-label="Поиск по документации">
            <Search aria-hidden="true" /><span>Поиск по документации</span>
          </Link>
          <Link className="developer-app-link" to="/app">
            API Console <ArrowUpRight aria-hidden="true" />
          </Link>
        </div>
      </header>

      <main id="developer-main" className="developer-surface">
        <div className={`developer-frame ${overview ? 'is-overview' : ''}`}>
          <header className="developer-heading">
            <p className="developer-eyebrow">{t('developer.eyebrow')}</p>
            <h1>{title}</h1>
            <p>{copy}</p>
          </header>

          <nav className="developer-tabs" aria-label={t('developer.eyebrow')}>
            {navigation.map(item => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) => `developer-tab ${isActive ? 'is-active' : ''}`}
              >
                {t(item.label)}
              </NavLink>
            ))}
          </nav>

          {children}
        </div>
      </main>

      <footer className="developer-footer">
        <span>© 2026 Kolibri AI</span>
        <nav aria-label="Ссылки разработчика">
          <Link to="/docs">Документация</Link>
          <Link to="/security">Безопасность</Link>
          <Link to="/terms">Условия</Link>
        </nav>
      </footer>
    </div>
  )
}
