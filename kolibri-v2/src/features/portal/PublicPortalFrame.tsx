import type { ReactNode } from 'react'
import { Link, useLocation } from 'react-router'
import CartoonMascot from '@/components/CartoonMascot'

interface PublicPortalFrameProps {
  children: ReactNode
}

const navigation = [
  { to: '/', label: 'Продукт' },
  { to: '/pricing', label: 'Тарифы' },
  { to: '/security', label: 'Безопасность' },
  { to: '/developers', label: 'Разработчикам' },
]

export default function PublicPortalFrame({ children }: PublicPortalFrameProps) {
  const { pathname } = useLocation()

  return (
    <div className="public-landing">
      <a className="public-skip-link" href="#public-main">Перейти к содержанию</a>
      <header className="public-landing-header">
        <Link className="public-brand" to="/" aria-label="Kolibri AI — главная">
          <CartoonMascot size={38} />
          <span>Kolibri</span>
        </Link>
        <nav className="public-navigation" aria-label="Навигация по сайту">
          {navigation.map(item => (
            <Link key={item.to} to={item.to} aria-current={pathname === item.to ? 'page' : undefined}>
              {item.label}
            </Link>
          ))}
        </nav>
        <div className="public-header-actions">
          <Link className="public-text-link" to="/login">Войти</Link>
          <Link className="public-primary-link" to="/app">Открыть Kolibri</Link>
        </div>
      </header>

      <main id="public-main">{children}</main>

      <footer className="public-footer">
        <span>© 2026 Kolibri AI</span>
        <nav aria-label="Правовая информация">
          <Link to="/pricing">Тарифы</Link>
          <Link to="/security">Безопасность</Link>
          <Link to="/privacy">Конфиденциальность</Link>
          <Link to="/terms">Условия</Link>
          <Link to="/docs">Документация</Link>
        </nav>
      </footer>
    </div>
  )
}
