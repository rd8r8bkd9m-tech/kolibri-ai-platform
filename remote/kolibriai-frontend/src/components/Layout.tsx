import { useState, useEffect } from 'react'
import { Outlet, useLocation, NavLink, useNavigate } from 'react-router'
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
import MascotAnimation from './MascotAnimation'
import SearchModal from './SearchModal'

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

export interface LayoutOutletContext {
  openSearch: () => void
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

  useEffect(() => {
    if (!mobileMenuOpen) return
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = previousOverflow
    }
  }, [mobileMenuOpen])

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
  const isChat = location.pathname === '/chat'

  const closeMobileMenu = () => setMobileMenuOpen(false)

  const openRecentItem = (item: LibraryItem) => {
    if (item.source_type === 'estimate') navigate(`/estimates?edit=${item.source_id}`)
    else if (item.source_type === 'document') navigate(`/documents?edit=${item.source_id}`)
    closeMobileMenu()
  }

  const isActiveRoute = (path: string) => {
    if (path === '/') return location.pathname === '/'
    return location.pathname === path || location.pathname.startsWith(`${path}/`)
  }

  const openSearch = () => {
    setSearchOpen(true)
  }

  const openNewChat = () => {
    navigate('/chat')
    closeMobileMenu()
  }

  const openMobileSearch = () => {
    setSearchOpen(true)
    closeMobileMenu()
  }

  const openHelp = () => {
    navigate('/settings?tab=help')
    closeMobileMenu()
  }

  return (
    <div className="flex h-[100dvh] w-full overflow-hidden bg-[var(--bg-primary)]">
      {/* ===== DESKTOP SIDEBAR ===== */}
      {!isHome && (
        <aside className="hidden md:flex flex-col w-[var(--sidebar-width)] h-full border-r border-[var(--border-subtle)] bg-[var(--bg-secondary)] flex-shrink-0">
          {/* Logo */}
          <div className="flex items-center gap-3 px-4 h-14 flex-shrink-0">
            <MascotAnimation state="idle" className="h-7 w-7" decorative />
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
                    onClick={() => openRecentItem(item)}
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
            <button onClick={() => navigate('/settings?tab=help')} className="flex items-center gap-3 w-full px-3 py-2 rounded-[var(--radius-md)] text-[13px] text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)] transition-colors">
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
      <header className="fixed left-0 right-0 top-0 z-40 flex h-[var(--mobile-header-height)] items-end justify-between gap-3 border-b border-[var(--border-subtle)] bg-[var(--bg-primary)]/95 px-3 pb-2 pt-[env(safe-area-inset-top)] backdrop-blur-md md:hidden">
        <button
          type="button"
          onClick={() => setMobileMenuOpen(true)}
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[var(--radius-md)] hover:bg-[var(--bg-hover)] transition-colors"
          aria-label="Открыть меню"
          aria-controls="kolibri-mobile-menu"
          aria-expanded={mobileMenuOpen}
        >
          <Menu size={22} strokeWidth={1.8} />
        </button>
        <div className="flex min-w-0 items-center gap-2.5">
          <MascotAnimation state="idle" className="h-8 w-8" decorative />
          <span className="truncate text-[17px] font-medium">Колибри</span>
        </div>
        <button
          type="button"
          onClick={() => openSearch()}
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[var(--radius-md)] text-[var(--text-tertiary)] hover:bg-[var(--bg-hover)] transition-colors"
          aria-label="Поиск"
          title="Поиск"
        >
          <Search size={21} strokeWidth={1.8} />
        </button>
      </header>

      {/* ===== MOBILE DRAWER ===== */}
      {mobileMenuOpen && (
        <>
          <div
            className="md:hidden fixed inset-0 bg-black/30 z-50 animate-fadeIn"
            onClick={() => setMobileMenuOpen(false)}
          />
          <aside
            id="kolibri-mobile-menu"
            role="dialog"
            aria-modal="true"
            aria-label="Мобильное меню Колибри"
            className="fixed bottom-0 left-0 top-0 z-[60] flex flex-col border-r border-white/20 bg-[var(--bg-primary)]/95 shadow-xl backdrop-blur-xl animate-slideIn md:hidden"
            style={{ width: 'min(320px, 88vw)' }}
          >
            <div className="flex h-[var(--mobile-header-height)] flex-shrink-0 items-end justify-between border-b border-[var(--border-subtle)] px-4 pb-2 pt-[env(safe-area-inset-top)]">
              <div className="flex min-w-0 items-center gap-2.5">
                <MascotAnimation state="idle" className="h-8 w-8" decorative />
                <span className="truncate text-[17px] font-semibold">Колибри</span>
              </div>
              <button
                type="button"
                onClick={() => setMobileMenuOpen(false)}
                className="w-10 h-10 flex items-center justify-center rounded-[var(--radius-md)] hover:bg-[var(--bg-hover)]"
                aria-label="Закрыть меню"
              >
                <X size={22} />
              </button>
            </div>

            <div className="px-2 py-3 border-b border-[var(--border-subtle)] space-y-1 flex-shrink-0">
              <button
                type="button"
                onClick={openNewChat}
                className="flex items-center gap-3 w-full px-3.5 py-3 rounded-[var(--radius-md)] text-[16px] font-medium text-[var(--text-primary)] bg-[var(--bg-elevated)] hover:bg-[var(--bg-hover)] transition-colors"
              >
                <Plus size={20} strokeWidth={1.8} />
                <span>Новый чат</span>
              </button>
              <button
                type="button"
                onClick={openMobileSearch}
                className="flex items-center gap-3 w-full px-3.5 py-3 rounded-[var(--radius-md)] text-[16px] text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)] transition-colors"
              >
                <Search size={20} strokeWidth={1.8} />
                <span>Поиск</span>
              </button>
            </div>

            <nav className="flex-1 overflow-y-auto overscroll-contain p-2 space-y-0.5">
              {sidebarItems.map((item) => (
                <button
                  type="button"
                  key={item.to}
                  onClick={() => {
                    navigate(item.to)
                    closeMobileMenu()
                  }}
                  className={`flex items-center gap-3 w-full px-3.5 py-3 rounded-[var(--radius-md)] text-[16px] text-left transition-colors ${
                    isActiveRoute(item.to)
                      ? 'bg-[var(--accent-teal)]/10 text-[var(--accent-teal)] font-medium'
                      : 'text-[var(--text-secondary)] hover:bg-[var(--bg-hover)]'
                  }`}
                >
                  <item.icon size={20} strokeWidth={1.8} />
                  <span>{item.label}</span>
                </button>
              ))}

              <div className="pt-4 mt-3 border-t border-[var(--border-subtle)]">
                <div className="px-3 mb-2">
                  <span className="text-[13px] font-medium text-[var(--text-tertiary)] uppercase tracking-wider">Недавние</span>
                </div>
                {recentItems.length > 0 ? (
                  <div className="space-y-0.5">
                    {recentItems.map((item) => (
                      <button
                        type="button"
                        key={item.id}
                        onClick={() => openRecentItem(item)}
                        className="flex items-center gap-3 w-full px-3.5 py-3 rounded-[var(--radius-md)] text-[16px] text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)] transition-colors text-left"
                      >
                        {item.item_type === 'estimate' ? <Calculator size={19} strokeWidth={1.8} /> : <FileText size={19} strokeWidth={1.8} />}
                        <span className="truncate">{item.title}</span>
                      </button>
                    ))}
                  </div>
                ) : (
                  <div className="px-3.5 py-2.5 text-[15px] text-[var(--text-tertiary)]">Пока нет недавних</div>
                )}
              </div>
            </nav>

            <div className="border-t border-[var(--border-subtle)] p-2 pb-[calc(env(safe-area-inset-bottom)+0.5rem)] space-y-0.5 flex-shrink-0">
              <button
                type="button"
                onClick={() => {
                  navigate('/settings')
                  closeMobileMenu()
                }}
                className={`flex items-center gap-3 w-full px-3.5 py-3 rounded-[var(--radius-md)] text-[16px] text-left transition-colors ${
                  isActiveRoute('/settings')
                    ? 'bg-[var(--accent-teal)]/10 text-[var(--accent-teal)] font-medium'
                    : 'text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)]'
                }`}
              >
                <Settings size={20} strokeWidth={1.8} />
                <span>Настройки</span>
              </button>
              <button type="button" onClick={openHelp} className="flex items-center gap-3 w-full px-3.5 py-3 rounded-[var(--radius-md)] text-[16px] text-left text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)] transition-colors">
                <HelpCircle size={20} strokeWidth={1.8} />
                <span>Помощь</span>
              </button>
              {user ? (
                <div className="flex items-center gap-3 px-3.5 py-3">
                  <div className="w-9 h-9 rounded-full bg-[var(--accent-teal)]/10 text-[var(--accent-teal)] flex items-center justify-center flex-shrink-0">
                    <User size={17} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-[15px] font-medium text-[var(--text-primary)] truncate">{user.name}</p>
                    <p className="text-[13px] text-[var(--text-tertiary)] truncate">{user.email}</p>
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      onLogout?.()
                      closeMobileMenu()
                    }}
                    className="w-10 h-10 flex items-center justify-center rounded-[var(--radius-md)] text-[var(--text-tertiary)] hover:bg-[var(--bg-hover)] hover:text-[var(--status-error)] transition-colors"
                    title="Выйти"
                  >
                    <LogOut size={18} />
                  </button>
                </div>
              ) : (
                <button
                  type="button"
                  onClick={() => {
                    navigate('/login')
                    closeMobileMenu()
                  }}
                  className="flex items-center gap-3 w-full px-3.5 py-3 rounded-[var(--radius-md)] text-[16px] text-left text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)] transition-colors"
                >
                  <LogIn size={20} strokeWidth={1.8} />
                  <span>Войти</span>
                </button>
              )}
            </div>
          </aside>
        </>
      )}

      {/* ===== MAIN CONTENT ===== */}
      <main className={`h-full flex-1 pt-[var(--mobile-header-height)] md:pt-0 ${isChat ? 'overflow-hidden' : 'overflow-y-auto'}`}>
        <Outlet context={{ openSearch } satisfies LayoutOutletContext} />
      </main>

      <SearchModal open={searchOpen} onClose={() => setSearchOpen(false)} />
    </div>
  )
}
