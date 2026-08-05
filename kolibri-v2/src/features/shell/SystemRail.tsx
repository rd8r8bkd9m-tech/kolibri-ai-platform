import { Building2, FileSignature, FolderOpen, PanelLeftClose, Settings, SquarePen, UserRound } from 'lucide-react'
import type { Project } from '@/lib/api'
import { useLocale } from '@/features/localization'
import RecentProjectItem from './RecentProjectItem'

interface SystemRailProps {
  expanded: boolean
  activePath: string
  onCollapse: () => void
  onNew: () => void
  onSettings: () => void
  onContracts: () => void
  onFiles: () => void
  onObjects: () => void
  onClients: () => void
  recentItems: Project[]
  onRecent: (projectId: string) => void
  onRename: (projectId: string, title: string) => Promise<Project>
  onTogglePin: (project: Project) => Promise<Project>
  onDelete: (projectId: string) => Promise<Project>
}

export default function SystemRail({
  expanded,
  activePath,
  onCollapse,
  onNew,
  onSettings,
  onContracts,
  onFiles,
  onObjects,
  onClients,
  recentItems,
  onRecent,
  onRename,
  onTogglePin,
  onDelete,
}: SystemRailProps) {
  const { t } = useLocale()

  return (
    <aside
      className={`shell-system-rail ${expanded ? 'is-expanded' : ''}`}
      aria-label={t('shell.navigation')}
      aria-hidden={!expanded}
      inert={!expanded ? true : undefined}
    >
      <header className="shell-history-header">
        <strong>Kolibri</strong>
        <button
          type="button"
          aria-label={t('shell.unpinMenu')}
          onClick={event => {
            event.currentTarget.blur()
            onCollapse()
          }}
        >
          <PanelLeftClose size={20} strokeWidth={1.8} />
        </button>
      </header>

      <button type="button" className="shell-history-new" onClick={onNew}>
        <SquarePen size={19} strokeWidth={1.8} />
        <span>{t('shell.newProject')}</span>
      </button>

      <nav className="shell-workspace-navigation" aria-label={t('drawer.mainNavigation')}>
        <button type="button" className={activePath === '/contracts' ? 'is-active' : undefined} aria-current={activePath === '/contracts' ? 'page' : undefined} onClick={onContracts}>
        <FileSignature size={19} strokeWidth={1.8} />
        <span>{t('shell.contracts')}</span>
        </button>
        <button type="button" className={activePath === '/library' ? 'is-active' : undefined} aria-current={activePath === '/library' ? 'page' : undefined} onClick={onFiles}>
          <FolderOpen size={19} strokeWidth={1.8} />
          <span>{t('shell.files')}</span>
        </button>
        <button type="button" className={activePath === '/objects' ? 'is-active' : undefined} aria-current={activePath === '/objects' ? 'page' : undefined} onClick={onObjects}>
          <Building2 size={19} strokeWidth={1.8} />
          <span>Объекты</span>
        </button>
        <button type="button" className={activePath === '/clients' ? 'is-active' : undefined} aria-current={activePath === '/clients' ? 'page' : undefined} onClick={onClients}>
          <UserRound size={19} strokeWidth={1.8} />
          <span>Заказчики</span>
        </button>
      </nav>

      <nav className="shell-history-list" aria-label={t('history.title')}>
        <p>{t('shell.recent')}</p>
        {recentItems.length ? recentItems.slice(0, 30).map(project => (
          <RecentProjectItem key={project.id} project={project} variant="rail" onOpen={onRecent} onRename={onRename} onTogglePin={onTogglePin} onDelete={onDelete} />
        )) : <span>{t('drawer.empty')}</span>}
      </nav>

      <button type="button" className="shell-history-settings" onClick={onSettings}>
        <Settings size={19} strokeWidth={1.8} />
        <span>{t('common.settings')}</span>
      </button>
    </aside>
  )
}
