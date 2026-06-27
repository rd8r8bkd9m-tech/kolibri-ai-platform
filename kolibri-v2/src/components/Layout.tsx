import { useState, useEffect } from 'react'
import { Outlet, useLocation, NavLink, useNavigate } from 'react-router'
/* Animation via CSS */
import {
  MessageSquare,
  Library,
  LayoutGrid,
  Calculator,
  FileText,
  Bot,
  Server,
  Settings,
  Menu,
  X,
  Plus,
  Search,
  HelpCircle,
  LogIn,
  LogOut,
  User,
} from 'lucide-react'
import type { AuthUser } from '@/lib/api'
import { library, type LibraryItem } from '@/lib/api'
import SearchModal from './SearchModal'

interface LayoutProps {
  user?: AuthUser | null
  onLogout?: () => void
}

const sidebarItems = [
  { to: '/chat', icon: MessageSquare, label: 'Чат' },
  { to: '/library', icon: Library, label: 'Библиотека' },
  { to: '/apps', icon: LayoutGrid, label: 'Приложения' },
  { to: '/estimates', icon: Calculator, label: 'Сметы' },
  { to: '/documents', icon: FileText, label: 'Документы' },
  { to: '/agents', icon: Bot, label: 'Агенты' },
  { to: '/servers', icon: Server, label: 'Серверы' },
]

interface LayoutProps {
  user?: AuthUser | null
  onLogout?: () => void
}

export default function Layout({ user, onLogout }: LayoutProps) {
  const location = useLocation()
  const navigate = useNavigate()
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [searchOpen, setSearchOpen] = useState(false)
  const [recentItems, setRecentItems] = useState<LibraryItem[]>([])

  // Load recent items
  useEffect(() => {
    library.list({ page_size: 5 }).then(data => setRecentItems(data.items)).catch(() => {})
  }, [])

  // Ctrl+K to open search
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        setSearchOpen(prev => !prev)
      }
      if ((e.metaKey || e.ctrlKey) && e.key === 'l') {
        e.preventDefault()
        navigate('/library')
      }
      if ((e.metaKey || e.ctrlKey) && e.key === ',') {
        e.preventDefault()
        navigate('/settings')
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [navigate])

  const isHome = location.pathname === '/'

  return (
    <div className="flex h-[100dvh] w-full overflow-hidden bg-[var(--bg-primary)]">
      {/* ===== DESKTOP SIDEBAR ===== */}
      {!isHome && (
        <aside className="hidden md:flex flex-col w-[var(--sidebar-width)] h-full border-r border-[var(--border-subtle)] bg-[var(--bg-secondary)] flex-shrink-0">
          {/* Logo */}
          <div className="flex items-center gap-3 px-4 h-14 flex-shrink-0">
            <img src="/kolibri-bird.png" alt="Колибри" className="w-7 h-7 object-contain" />
            <span className="font-semibold text-[15px] text-[var(--text-primary)] tracking-tight">Колибри</span>
          </div>

          {/* New Chat Button */}
          <div className="px-3 mb-2">
            <NavLink
              to="/"
              className="flex items-center gap-2.5 px-3 py-2 rounded-[var(--radius-md)] text-[13px] font-medium text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)] transition-colors"
            >
              <Plus size={16} />
              <span>Новый чат</span>
            </NavLink>
          </div>

          {/* Search */}
          <div className="px-3 mb-3">
            <button onClick={() => setSearchOpen(true)} className="flex items-center gap-2.5 w-full px-3 py-2 rounded-[var(--radius-md)] text-[13px] text-[var(--text-tertiary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-secondary)] transition-colors">
              <Search size={15} />
              <span>Поиск</span>
              <kbd className="ml-auto text-[11px] font-mono text-[var(--text-tertiary)] bg-[var(--bg-elevated)] px-1.5 py-0.5 rounded">Ctrl K</kbd>
            </button>
          </div>

          {/* Nav Items */}
          <nav className="flex-1 overflow-y-auto px-2 space-y-0.5">
            {sidebarItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-3 py-2 rounded-[var(--radius-md)] text-[13px] transition-colors ${
                    isActive
                      ? 'bg-[var(--accent-teal)]/10 text-[var(--accent-teal)] font-medium'
                      : 'text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)]'
                  }`
                }
              >
                <item.icon size={17} strokeWidth={1.8} />
                <span>{item.label}</span>
              </NavLink>
            ))}

            {/* Recent */}
            {recentItems.length > 0 && (
              <>
                <div className="mt-6 mb-2 px-3">
                  <span className="text-[11px] font-medium text-[var(--text-tertiary)] uppercase tracking-wider">Недавние</span>
                </div>
                {recentItems.map((item) => (
                  <button
                    key={item.id}
                    onClick={() => {
                      if (item.source_type === 'estimate') navigate(`/estimates?edit=${item.source_id}`)
                      else if (item.source_type === 'document') navigate(`/documents?edit=${item.source_id}`)
                      setMobileMenuOpen(false)
                    }}
                    className="flex items-center gap-3 w-full px-3 py-2 rounded-[var(--radius-md)] text-[13px] text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)] transition-colors text-left"
                  >
                    {item.item_type === 'estimate' ? <Calculator size={15} strokeWidth={1.8} /> : <FileText size={15} strokeWidth={1.8} />}
                    <span className="truncate">{item.title}</span>
                  </button>
                ))}
              </>
            )}
          </nav>

          {/* Bottom */}
          <div className="border-t border-[var(--border-subtle)] p-2 space-y-0.5 flex-shrink-0">
            <NavLink
              to="/settings"
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded-[var(--radius-md)] text-[13px] transition-colors ${
                  isActive
                    ? 'bg-[var(--accent-teal)]/10 text-[var(--accent-teal)] font-medium'
                    : 'text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)]'
                }`
              }
            >
              <Settings size={17} strokeWidth={1.8} />
              <span>Настройки</span>
            </NavLink>
            <button onClick={() => navigate('/settings')} className="flex items-center gap-3 w-full px-3 py-2 rounded-[var(--radius-md)] text-[13px] text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)] transition-colors">
              <HelpCircle size={17} strokeWidth={1.8} />
              <span>Помощь</span>
            </button>
            {user ? (
              <div className="flex items-center gap-3 px-3 py-2">
                <div className="w-7 h-7 rounded-full bg-[var(--accent-teal)]/10 text-[var(--accent-teal)] flex items-center justify-center">
                  <User size={14} />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-[12px] font-medium text-[var(--text-primary)] truncate">{user.name}</p>
                  <p className="text-[10px] text-[var(--text-tertiary)] truncate">{user.email}</p>
                </div>
                <button onClick={onLogout} className="w-6 h-6 flex items-center justify-center rounded text-[var(--text-tertiary)] hover:text-[var(--status-error)] transition-colors" title="Выйти">
                  <LogOut size={14} />
                </button>
              </div>
            ) : (
              <NavLink to="/login" className="flex items-center gap-3 px-3 py-2 rounded-[var(--radius-md)] text-[13px] text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)] transition-colors">
                <LogIn size={17} strokeWidth={1.8} />
                <span>Войти</span>
              </NavLink>
            )}
          </div>
        </aside>
      )}

      {/* ===== MOBILE HEADER ===== */}
      {!isHome && (
        <header className="md:hidden fixed top-0 left-0 right-0 h-12 bg-[var(--bg-primary)]/90 backdrop-blur-md border-b border-[var(--border-subtle)] z-50 flex items-center px-3 gap-3">
          <button
            onClick={() => setMobileMenuOpen(true)}
            className="w-8 h-8 flex items-center justify-center rounded-[var(--radius-md)] hover:bg-[var(--bg-hover)] transition-colors"
          >
            <Menu size={20} strokeWidth={1.8} />
          </button>
          <img src="/kolibri-bird.png" alt="" className="w-6 h-6 object-contain" />
          <span className="font-medium text-[14px]">Колибри</span>
        </header>
      )}

      {/* ===== MOBILE DRAWER ===== */}
      {mobileMenuOpen && (
        <>
          <div
            className="md:hidden fixed inset-0 bg-black/30 z-50 animate-fadeIn"
            onClick={() => setMobileMenuOpen(false)}
          />
          <aside
            className="md:hidden fixed top-0 left-0 bottom-0 w-[260px] bg-[var(--bg-primary)] z-50 shadow-xl flex flex-col animate-slideIn"
          >
              <div className="flex items-center justify-between px-4 h-12 border-b border-[var(--border-subtle)] flex-shrink-0">
                <div className="flex items-center gap-2.5">
                  <img src="/kolibri-bird.png" alt="" className="w-6 h-6 object-contain" />
                  <span className="font-semibold text-[14px]">Колибри</span>
                </div>
                <button onClick={() => setMobileMenuOpen(false)} className="w-8 h-8 flex items-center justify-center rounded-[var(--radius-md)] hover:bg-[var(--bg-hover)]">
                  <X size={20} />
                </button>
              </div>
              <nav className="flex-1 overflow-y-auto p-2 space-y-0.5">
                {sidebarItems.map((item) => (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    onClick={() => setMobileMenuOpen(false)}
                    className={({ isActive }) =>
                      `flex items-center gap-3 px-3 py-2.5 rounded-[var(--radius-md)] text-[14px] transition-colors ${
                        isActive
                          ? 'bg-[var(--accent-teal)]/10 text-[var(--accent-teal)] font-medium'
                          : 'text-[var(--text-secondary)] hover:bg-[var(--bg-hover)]'
                      }`
                    }
                  >
                    <item.icon size={18} strokeWidth={1.8} />
                    <span>{item.label}</span>
                  </NavLink>
                ))}
              </nav>
          </aside>
        </>
      )}

      {/* ===== MAIN CONTENT ===== */}
      <main className={`flex-1 h-full overflow-y-auto ${!isHome ? 'md:pt-0 pt-12' : ''}`}>
        <Outlet />
      </main>

      <SearchModal open={searchOpen} onClose={() => setSearchOpen(false)} />
    </div>
  )
}
