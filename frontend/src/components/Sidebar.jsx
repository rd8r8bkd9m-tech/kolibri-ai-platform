import { motion, AnimatePresence } from "framer-motion"
import {
  BarChart3,
  Bot,
  ClipboardList,
  Files,
  LayoutDashboard,
  MessageSquare,
  Network,
  Plus,
  Search,
  Server,
  X,
} from "lucide-react"
import { KolibriBird } from "./KolibriBird"

export function Sidebar({
  sidebar,
  setSidebar,
  birdState,
  activeTab,
  setActiveTab,
  clusterStatus,
  conversations,
  conversationId,
  loadConversation,
  deleteConversation,
  providers,
  selectedProvider,
  setSelectedProvider,
  theme,
  setTheme,
  connected,
  onNewChat,
}) {
  const navItems = [
    { id: "overview", label: "Overview", desc: "Операционный центр", icon: <LayoutDashboard size={18} /> },
    { id: "agents", label: "Agents", desc: "Команда агентов", icon: <Bot size={18} /> },
    { id: "tasks", label: "Tasks", desc: "Manifests и gates", icon: <ClipboardList size={18} />, badge: "4" },
    { id: "servers", label: "Servers", desc: `${clusterStatus?.online_nodes || 0} онлайн`, icon: <Server size={18} />, badge: clusterStatus?.online_nodes },
    { id: "reports", label: "Reports", desc: "10:00 / 18:00 MSK", icon: <BarChart3 size={18} /> },
    { id: "chat", label: "Chat", desc: "Диалог с AI", icon: <MessageSquare size={18} /> },
    { id: "documents", label: "Docs", desc: "База знаний", icon: <Files size={18} /> },
    { id: "search", label: "Search", desc: "Семантический поиск", icon: <Search size={18} /> },
    { id: "cluster", label: "Network", desc: "Raw cluster status", icon: <Network size={18} /> },
  ]

  const handleNavClick = (id) => {
    setActiveTab(id)
    setSidebar(false)
  }

  return (
    <>
      {/* Desktop sidebar */}
      <aside className="sidebar">
        <div className="sidebar-header">
          <div className="sidebar-logo">
            <KolibriBird size={36} state={birdState} />
            <span className="sidebar-logo-text">Kolibri</span>
            <span className="sidebar-logo-badge">AI</span>
          </div>
          <motion.button className="new-chat-btn" onClick={onNewChat} aria-label="Новый чат"
            whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>
            <Plus size={14} strokeWidth={2.5} />
            Новый чат
          </motion.button>
        </div>

        <nav className="sidebar-nav">
          {navItems.map(item => (
            <motion.button key={item.id} className={`sidebar-nav-item ${activeTab === item.id ? "active" : ""}`}
              onClick={() => handleNavClick(item.id)}
              whileHover={{ x: 2 }} whileTap={{ scale: 0.98 }}>
              {item.icon}{item.label}
              {item.badge ? <span className="nav-badge">{item.badge}</span> : null}
            </motion.button>
          ))}
        </nav>

        {conversations.length > 0 && (
          <div className="sidebar-section conversation-list-section">
            <div className="sidebar-label">История</div>
            <div className="conversation-list">
              {conversations.slice(0, 20).map(c => (
                <div key={c.id} className={`conversation-item ${c.id === conversationId ? "active" : ""}`}>
                  <button className="conversation-item-btn" onClick={() => loadConversation(c.id)}>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ flexShrink: 0, opacity: 0.5 }}>
                      <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/>
                    </svg>
                    <span className="conversation-item-title">{c.title || "Без названия"}</span>
                  </button>
                  <button className="conversation-delete-btn" aria-label="Удалить диалог" onClick={(e) => { e.stopPropagation(); deleteConversation(c.id) }}>
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="sidebar-section">
          <div className="sidebar-label">Модель</div>
          <select className="sidebar-select" value={selectedProvider} onChange={e => setSelectedProvider(e.target.value)}>
            {providers.filter(p => p.available).map(p => (
              <option key={p.name} value={p.name}>
                {p.name === "formulalm" ? "Kolibri Nano (local)" : p.name === "mimo" ? "MiMo Cloud" : p.name}
              </option>
            ))}
            {providers.length === 0 && <option value="mimo">MiMo Cloud</option>}
          </select>
        </div>

        <div className="sidebar-section">
          <div className="sidebar-label">Тема</div>
          <motion.div className="theme-switch" onClick={() => setTheme(theme === "light" ? "dark" : "light")}
            tabIndex={0} role="switch" aria-checked={theme === "dark"} aria-label="Переключить тему"
            onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setTheme(theme === "light" ? "dark" : "light") } }}
            whileTap={{ scale: 0.98 }}>
            <span className="theme-switch-label">{theme === "light" ? "Светлая" : "Тёмная"}</span>
            <div className={`theme-switch-toggle ${theme === "dark" ? "active" : ""}`}></div>
          </motion.div>
        </div>

        <div className="sidebar-footer">
          <div className="connection-status">
            <motion.div className={`connection-dot ${connected ? "connected" : ""}`}
              animate={connected ? { scale: [1, 1.3, 1] } : {}}
              transition={{ duration: 2, repeat: Infinity }} />
            {connected ? "Подключено к AI" : "Отключено"}
          </div>
        </div>
      </aside>

      {/* Mobile menu */}
      <div className="mobile-only">
        <AnimatePresence>
          {sidebar && (
            <motion.div
              className="mobile-menu-overlay"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setSidebar(false)}
            />
          )}
        </AnimatePresence>

        <AnimatePresence>
          {sidebar && (
            <motion.aside
              className="mobile-menu"
              initial={{ x: "-100%" }}
              animate={{ x: 0 }}
              exit={{ x: "-100%" }}
              transition={{ type: "spring", damping: 25, stiffness: 200 }}
            >
              <div className="mobile-menu-header">
                <div className="mobile-menu-logo">
                  <KolibriBird size={48} state={birdState} />
                  <div>
                    <div className="mobile-menu-title">Kolibri AI</div>
                    <div className="mobile-menu-subtitle">
                      {connected ? "Подключено" : "Отключено"}
                      {clusterStatus && ` · ${clusterStatus.online_nodes} серверов`}
                    </div>
                  </div>
                </div>
                <button className="mobile-menu-close" onClick={() => setSidebar(false)}>
                  <X size={24} />
                </button>
              </div>

              <motion.button
                className="mobile-menu-new-chat"
                onClick={() => { onNewChat(); setSidebar(false) }}
                whileTap={{ scale: 0.97 }}
              >
                <Plus size={20} strokeWidth={2.5} />
                Новый чат
              </motion.button>

              <div className="mobile-menu-section">
                <div className="mobile-menu-section-title">Навигация</div>
                {navItems.map((item, i) => (
                  <motion.button
                    key={item.id}
                    className={`mobile-menu-item ${activeTab === item.id ? "active" : ""}`}
                    onClick={() => handleNavClick(item.id)}
                    initial={{ opacity: 0, x: -20 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: i * 0.05 }}
                    whileTap={{ scale: 0.97 }}
                  >
                    <div className="mobile-menu-item-icon">{item.icon}</div>
                    <div>
                      <div className="mobile-menu-item-label">{item.label}</div>
                      <div className="mobile-menu-item-desc">{item.desc}</div>
                    </div>
                  </motion.button>
                ))}
              </div>

              {conversations.length > 0 && (
                <div className="mobile-menu-section">
                  <div className="mobile-menu-section-title">История</div>
                  <div className="mobile-menu-history">
                    {conversations.slice(0, 10).map((c, i) => (
                      <motion.div
                        key={c.id}
                        className={`mobile-menu-history-item ${c.id === conversationId ? "active" : ""}`}
                        initial={{ opacity: 0, x: -20 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: 0.2 + i * 0.03 }}
                        style={{ display: "flex", alignItems: "center", gap: "12px" }}
                      >
                        <button
                          onClick={() => { loadConversation(c.id); setSidebar(false) }}
                          style={{ flex: 1, display: "flex", alignItems: "center", gap: "12px", background: "none", border: "none", color: "inherit", cursor: "pointer", font: "inherit", padding: 0 }}
                        >
                          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/>
                          </svg>
                          <span>{c.title || "Без названия"}</span>
                        </button>
                        <button
                          className="mobile-menu-delete-btn"
                          onClick={(e) => { e.stopPropagation(); deleteConversation(c.id) }}
                        >
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                          </svg>
                        </button>
                      </motion.div>
                    ))}
                  </div>
                </div>
              )}

              <div className="mobile-menu-section">
                <div className="mobile-menu-section-title">Настройки</div>
                <div className="mobile-menu-item">
                  <div className="mobile-menu-item-icon">
                    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-2 2 2 2 0 01-2-2v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83 0 2 2 0 010-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 01-2-2 2 2 0 012-2h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 010-2.83 2 2 0 012.83 0l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 012-2 2 2 0 012 2v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 0 2 2 0 010 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 012 2 2 2 0 01-2 2h-.09a1.65 1.65 0 00-1.51 1z"/>
                    </svg>
                  </div>
                  <div style={{ flex: 1 }}>
                    <div className="mobile-menu-item-label">Модель</div>
                    <select
                      className="mobile-menu-select"
                      value={selectedProvider}
                      onChange={e => setSelectedProvider(e.target.value)}
                    >
                      {providers.filter(p => p.available).map(p => (
                        <option key={p.name} value={p.name}>
                          {p.name === "formulalm" ? "Kolibri Nano (local)" : p.name === "mimo" ? "MiMo Cloud" : p.name}
                        </option>
                      ))}
                      {providers.length === 0 && <option value="mimo">MiMo Cloud</option>}
                    </select>
                  </div>
                </div>

                <motion.button
                  className="mobile-menu-item"
                  onClick={() => setTheme(theme === "light" ? "dark" : "light")}
                  whileTap={{ scale: 0.97 }}
                >
                  <div className="mobile-menu-item-icon">
                    {theme === "dark" ? (
                      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
                      </svg>
                    ) : (
                      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/>
                      </svg>
                    )}
                  </div>
                  <div>
                    <div className="mobile-menu-item-label">{theme === "dark" ? "Светлая тема" : "Тёмная тема"}</div>
                    <div className="mobile-menu-item-desc">Переключить оформление</div>
                  </div>
                </motion.button>
              </div>

              <div className="mobile-menu-footer">
                <div className={`mobile-menu-status ${connected ? "online" : "offline"}`}>
                  <div className="mobile-menu-status-dot" />
                  {connected ? "AI онлайн" : "AI офлайн"}
                </div>
              </div>
            </motion.aside>
          )}
        </AnimatePresence>
      </div>
    </>
  )
}
