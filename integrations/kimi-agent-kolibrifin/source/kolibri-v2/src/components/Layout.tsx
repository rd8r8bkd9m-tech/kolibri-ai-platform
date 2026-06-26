import { useState } from 'react'
import { Outlet, useLocation, NavLink } from 'react-router'
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
  Clock,
  HelpCircle,
} from 'lucide-react'

const sidebarItems = [
  { to: '/chat', icon: MessageSquare, label: 'Чат' },
  { to: '/library', icon: Library, label: 'Библиотека' },
  { to: '/apps', icon: LayoutGrid, label: 'Приложения' },
  { to: '/estimates', icon: Calculator, label: 'Сметы' },
  { to: '/documents', icon: FileText, label: 'Документы' },
  { to: '/agents', icon: Bot, label: 'Агенты' },
  { to: '/servers', icon: Server, label: 'Серверы' },
]

const recentChats = [
  { id: '1', title: 'Смета на электромонтаж' },
  { id: '2', title: 'Договор подряда №45' },
  { id: '3', title: 'Анализ продаж Q4' },
  { id: '4', title: 'React компоненты' },
  { id: '5', title: 'Прайс-лист материалов' },
]

export default function Layout() {
  const location = useLocation()
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

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
            <button className="flex items-center gap-2.5 w-full px-3 py-2 rounded-[var(--radius-md)] text-[13px] text-[var(--text-tertiary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-secondary)] transition-colors">
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
            <div className="mt-6 mb-2 px-3">
              <span className="text-[11px] font-medium text-[var(--text-tertiary)] uppercase tracking-wider">Недавние</span>
            </div>
            {recentChats.map((chat) => (
              <button
                key={chat.id}
                className="flex items-center gap-3 w-full px-3 py-2 rounded-[var(--radius-md)] text-[13px] text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)] transition-colors text-left"
              >
                <Clock size={15} strokeWidth={1.8} />
                <span className="truncate">{chat.title}</span>
              </button>
            ))}
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
            <button className="flex items-center gap-3 w-full px-3 py-2 rounded-[var(--radius-md)] text-[13px] text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)] transition-colors">
              <HelpCircle size={17} strokeWidth={1.8} />
              <span>Помощь</span>
            </button>
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
    </div>
  )
}
