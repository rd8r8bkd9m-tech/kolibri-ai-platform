import { useEffect, useMemo, useState } from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router'
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
  const [railExpanded, setRailExpanded] = useState(false)
  const [railPinned, setRailPinned] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [searchOpen, setSearchOpen] = useState(false)
  const [voiceModeActive, setVoiceModeActive] = useState(false)
  const [conversationHasContent, setConversationHasContent] = useState(false)
  const { projects, error: historyError, deleteProject, restoreProject } = useProjectHistory()

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
    if (location.pathname === '/library') return t('shell.files')
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
            expanded={railExpanded || railPinned}
            pinned={railPinned}
            onExpandedChange={setRailExpanded}
            onPinnedChange={setRailPinned}
            onNew={() => navigate('/chat')}
            onHistory={() => setHistoryOpen(true)}
            onSearch={() => setSearchOpen(true)}
            onFiles={() => navigate('/library')}
            onSettings={() => navigate('/settings')}
          />

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
            onClose={() => setMobileOpen(false)}
            onNavigate={mobileAction}
            onNew={() => navigate('/chat')}
            onHistory={() => setHistoryOpen(true)}
            onSearch={() => setSearchOpen(true)}
            onFiles={() => navigate('/library')}
            onAgents={() => navigate('/control')}
            showOwnerControl={isOwnerRole(user?.role)}
            onSettings={() => navigate('/settings')}
            recentItems={projects}
            onRecent={selectHistoryItem}
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
