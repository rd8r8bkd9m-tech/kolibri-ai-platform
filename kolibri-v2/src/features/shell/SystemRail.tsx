import { PanelLeftClose, Settings, SquarePen } from 'lucide-react'
import type { Project } from '@/lib/api'
import { useLocale } from '@/features/localization'

interface SystemRailProps {
  expanded: boolean
  onCollapse: () => void
  onNew: () => void
  onSettings: () => void
  recentItems: Project[]
  onRecent: (projectId: string) => void
}

export default function SystemRail({
  expanded,
  onCollapse,
  onNew,
  onSettings,
  recentItems,
  onRecent,
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
        <button type="button" aria-label={t('shell.unpinMenu')} onClick={onCollapse}>
          <PanelLeftClose size={20} strokeWidth={1.8} />
        </button>
      </header>

      <button type="button" className="shell-history-new" onClick={onNew}>
        <SquarePen size={19} strokeWidth={1.8} />
        <span>{t('shell.newProject')}</span>
      </button>

      <nav className="shell-history-list" aria-label={t('history.title')}>
        <p>{t('shell.recent')}</p>
        {recentItems.length ? recentItems.slice(0, 30).map(project => (
          <button type="button" key={project.id} onClick={() => onRecent(project.id)}>
            {project.title}
          </button>
        )) : <span>{t('drawer.empty')}</span>}
      </nav>

      <button type="button" className="shell-history-settings" onClick={onSettings}>
        <Settings size={19} strokeWidth={1.8} />
        <span>{t('common.settings')}</span>
      </button>
    </aside>
  )
}
