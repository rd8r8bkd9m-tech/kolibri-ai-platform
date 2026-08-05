import { useState, type ReactNode } from 'react'
import { ArrowUpRight, Menu, Search, X } from 'lucide-react'
import { Link, useLocation } from 'react-router'
import CartoonMascot from '@/components/CartoonMascot'

interface PublicPortalFrameProps {
  children: ReactNode
}

const navigation = [
  { to: '/', label: 'Продукт' },
  { to: '/pricing', label: 'Тарифы' },
  { to: '/developers', label: 'API' },
  { to: '/docs', label: 'Документация' },
  { to: '/security', label: 'Безопасность' },
]

const homeNavigation = [
  { to: '#workflow', label: 'Начать диалог' },
  { to: '/pricing', label: 'Тарифы' },
  { to: '/security', label: 'Безопасность' },
  { to: '/developers', label: 'API' },
]

export default function PublicPortalFrame({ children }: PublicPortalFrameProps) {
  const { pathname } = useLocation()
  const [menuOpen, setMenuOpen] = useState(false)
  const visibleNavigation = pathname === '/' ? homeNavigation : navigation

  return (
    <div className={`public-landing${pathname === '/' ? ' is-home' : ''}`}>
      <a className="public-skip-link" href="#public-main">Перейти к содержанию</a>
      <header className="public-landing-header">
        <Link className="public-brand" to="/" aria-label="Kolibri AI — главная">
          <CartoonMascot size={38} />
          <span>Kolibri <b>AI</b></span>
        </Link>
        <nav className="public-navigation" aria-label="Навигация по сайту">
          {visibleNavigation.map(item => item.to.startsWith('#') ? (
            <a key={item.to} href={item.to}>{item.label}</a>
          ) : (
            <Link key={item.to} to={item.to} aria-current={pathname === item.to ? 'page' : undefined}>{item.label}</Link>
          ))}
        </nav>
        <div className="public-header-actions">
          {pathname !== '/' && <Link className="public-search-link" to="/docs" aria-label="Поиск по документации">
            <Search aria-hidden="true" /><span>Поиск</span>
          </Link>}
          <Link className="public-text-link" to="/login">Войти</Link>
          <Link className="public-primary-link" to="/app">{pathname === '/' ? 'Открыть' : 'Открыть Kolibri'} <ArrowUpRight aria-hidden="true" /></Link>
          <button
            type="button"
            className="public-menu-button"
            aria-label={menuOpen ? 'Закрыть меню' : 'Открыть меню'}
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen(value => !value)}
          >
            {menuOpen ? <X aria-hidden="true" /> : <Menu aria-hidden="true" />}
          </button>
        </div>
      </header>

      {menuOpen && (
        <nav className="public-mobile-navigation" aria-label="Мобильная навигация">
          {visibleNavigation.map(item => item.to.startsWith('#') ? (
            <a key={item.to} href={item.to} onClick={() => setMenuOpen(false)}>{item.label}</a>
          ) : (
            <Link key={item.to} to={item.to} onClick={() => setMenuOpen(false)}>{item.label}</Link>
          ))}
          <Link to="/login" onClick={() => setMenuOpen(false)}>Войти</Link>
          <Link to="/app" onClick={() => setMenuOpen(false)}>Открыть Kolibri</Link>
        </nav>
      )}

      <main id="public-main">{children}</main>

      <footer className="public-footer">
        <span>© 2026 Kolibri AI</span>
        <nav aria-label="Правовая информация">
          <Link to="/developers">API</Link>
          <Link to="/control">Фабрика</Link>
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
