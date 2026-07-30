import { useEffect, useMemo, useState } from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router'
import { Equal } from 'lucide-react'
import SearchModal from './SearchModal'
import HistoryPanel from '@/features/shell/HistoryPanel'
import SystemRail from '@/features/shell/SystemRail'
import MobileShellHeader from '@/features/shell/MobileShellHeader'
import MobileNavigationDrawer from '@/features/shell/MobileNavigationDrawer'
import useMobileDrawerGesture from '@/features/shell/useMobileDrawerGesture'
import { CapabilityProvider } from '@/features/capabilities'
import { ExecutionPolicyProvider } from '@/features/shell/ExecutionPolicyProvider'
import { ProjectHistoryProvider } from '@/features/projects/ProjectHistoryProvider'
import { useProjectHistory } from '@/features/projects/projectHistoryContext'
import { useLocale } from '@/features/localization'
import { isOwnerRole } from '@/features/shell/releaseIdentity'
import type { AuthUser } from '@/lib/api'
import type { ShellOutletContext } from '@/features/auth/shellIdentity'

export default function Layout({ user }: { user: AuthUser | null }) {
  return (
    <ProjectHistoryProvider>
      <LayoutShell user={user} />
    </ProjectHistoryProvider>
  )
}

function LayoutShell({ user }: { user: AuthUser | null }) {
  const { t } = useLocale()
  const navigate = useNavigate()
  const location = useLocation()
  const [railPinned, setRailPinned] = useState(true)
  const [mobileOpen, setMobileOpen] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [searchOpen, setSearchOpen] = useState(false)
  const [voiceModeActive, setVoiceModeActive] = useState(false)
  const [conversationHasContent, setConversationHasContent] = useState(false)
  const { projects, error: historyError, deleteProject, restoreProject, updateProject } = useProjectHistory()

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        setSearchOpen(true)
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  useEffect(() => {
    const handleConversationState = (event: Event) => {
      const detail = (event as CustomEvent<{ populated?: boolean }>).detail
      setConversationHasContent(Boolean(detail?.populated))
    }
    window.addEventListener('kolibri:conversation-state', handleConversationState)
    return () => window.removeEventListener('kolibri:conversation-state', handleConversationState)
  }, [])

  useEffect(() => {
    const handleVoiceMode = (event: Event) => {
      const detail = (event as CustomEvent<{ active?: boolean }>).detail
      setVoiceModeActive(Boolean(detail?.active))
    }
    window.addEventListener('kolibri:voice-mode', handleVoiceMode)
    return () => window.removeEventListener('kolibri:voice-mode', handleVoiceMode)
  }, [])

  const title = useMemo(() => {
    if (location.pathname === '/estimates') return t('shell.estimate')
    if (location.pathname === '/documents') return t('shell.document')
    if (location.pathname === '/contracts') return t('shell.contracts')
    if (location.pathname === '/library') return t('shell.files')
    if (location.pathname === '/objects') return 'Объекты'
    if (location.pathname === '/clients') return 'Заказчики'
    return 'Kolibri'
  }, [location.pathname, t])

  const selectHistoryItem = (projectId: string) => {
    setHistoryOpen(false)
    navigate(`/chat/${encodeURIComponent(projectId)}`)
  }

  const deleteHistoryItem = async (projectId: string) => {
    const deleted = await deleteProject(projectId)
    if (location.pathname === `/chat/${encodeURIComponent(projectId)}`) {
      const nextProject = projects.find(item => item.id !== projectId)
      navigate(nextProject ? `/chat/${encodeURIComponent(nextProject.id)}` : '/chat', { replace: true })
    }
    return deleted
  }

  const renameHistoryItem = (projectId: string, title: string) => updateProject(projectId, { title })

  const togglePinnedHistoryItem = (project: (typeof projects)[number]) => updateProject(project.id, {
    metadata: { ...project.metadata, pinned: project.metadata.pinned !== true },
  })

  const mobileAction = (action: () => void) => {
    setMobileOpen(false)
    action()
  }

  const drawerGesture = useMobileDrawerGesture({
    open: mobileOpen,
    onOpen: () => setMobileOpen(true),
    onClose: () => setMobileOpen(false),
  })
  const conversationHome = location.pathname.replace(/\/+$/, '') === '/app'
  const conversationRoute = conversationHome || location.pathname.startsWith('/chat')

  return (
    <ExecutionPolicyProvider>
      <CapabilityProvider>
        <div className={`shell-root ${railPinned ? 'rail-pinned' : ''} ${mobileOpen ? 'is-mobile-navigation-open' : ''} ${conversationRoute ? 'is-conversation-route' : ''} ${conversationHome ? 'is-conversation-home-route' : ''}`} {...drawerGesture}>
          <SystemRail
            expanded={railPinned}
            activePath={location.pathname}
            onCollapse={() => setRailPinned(false)}
            onNew={() => navigate('/chat')}
            onSettings={() => navigate('/settings')}
            onEstimates={() => navigate('/estimates')}
            onContracts={() => navigate('/contracts')}
            onFiles={() => navigate('/library')}
            onObjects={() => navigate('/objects')}
            onClients={() => navigate('/clients')}
            recentItems={projects}
            onRecent={selectHistoryItem}
            onRename={renameHistoryItem}
            onTogglePin={togglePinnedHistoryItem}
            onDelete={deleteHistoryItem}
          />

          {!railPinned && (
            <button
              type="button"
              className="shell-desktop-sidebar-trigger"
              aria-label={t('shell.pinMenu')}
              onClick={() => setRailPinned(true)}
            >
              <Equal size={22} strokeWidth={1.8} />
            </button>
          )}

          <MobileShellHeader
            open={mobileOpen}
            title={title}
            conversationSurface={conversationRoute}
            conversationHome={conversationHome}
            conversationHasContent={!conversationHome && conversationHasContent}
            voiceModeActive={voiceModeActive}
            onToggle={() => setMobileOpen(value => !value)}
            onNewConversation={() => navigate('/chat')}
            onHistory={() => setHistoryOpen(true)}
            onFiles={() => navigate('/library')}
          />

          <MobileNavigationDrawer
            open={mobileOpen}
            activePath={location.pathname}
            onClose={() => setMobileOpen(false)}
            onNavigate={mobileAction}
            onNew={() => navigate('/chat')}
            onHistory={() => setHistoryOpen(true)}
            onSearch={() => setSearchOpen(true)}
            onFiles={() => navigate('/library')}
            onEstimates={() => navigate('/estimates')}
            onContracts={() => navigate('/contracts')}
            onObjects={() => navigate('/objects')}
            onClients={() => navigate('/clients')}
            onAgents={() => navigate('/control')}
            showOwnerControl={isOwnerRole(user?.role)}
            onSettings={() => navigate('/settings')}
            recentItems={projects}
            onRecent={selectHistoryItem}
            onRename={renameHistoryItem}
            onTogglePin={togglePinnedHistoryItem}
            onDelete={deleteHistoryItem}
            user={user}
          />

          <main className="shell-main">
            <Outlet context={{ user } satisfies ShellOutletContext} />
          </main>

          <HistoryPanel
            open={historyOpen}
            items={projects}
            error={historyError}
            onClose={() => setHistoryOpen(false)}
            onSelect={selectHistoryItem}
            onDelete={deleteHistoryItem}
            onRestore={restoreProject}
          />
          <SearchModal open={searchOpen} onClose={() => setSearchOpen(false)} />
        </div>
      </CapabilityProvider>
    </ExecutionPolicyProvider>
  )
}
