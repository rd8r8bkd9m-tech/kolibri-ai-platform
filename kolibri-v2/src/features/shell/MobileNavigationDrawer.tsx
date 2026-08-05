import { useEffect, useRef } from 'react'
import { Bot, Building2, FileSignature, FolderOpen, Search, Settings, SquarePen, UserRound, X } from 'lucide-react'
import type { AuthUser, Project } from '@/lib/api'
import { useLocale } from '@/features/localization'
import { verifiedDisplayName, verifiedInitials } from '@/features/auth/shellIdentity'
import RecentProjectItem from './RecentProjectItem'
import styles from './MobileNavigationDrawer.module.css'

interface MobileNavigationDrawerProps {
  open: boolean
  activePath: string
  onClose: () => void
  onNavigate: (action: () => void) => void
  onNew: () => void
  onHistory: () => void
  onSearch: () => void
  onFiles: () => void
  onContracts: () => void
  onObjects: () => void
  onClients: () => void
  onAgents: () => void
  showOwnerControl: boolean
  onSettings: () => void
  recentItems: Project[]
  onRecent: (projectId: string) => void
  onRename: (projectId: string, title: string) => Promise<Project>
  onTogglePin: (project: Project) => Promise<Project>
  onDelete: (projectId: string) => Promise<Project>
  user: AuthUser | null
}

export default function MobileNavigationDrawer({
  open,
  activePath,
  onClose,
  onNavigate,
  onNew,
  onHistory,
  onSearch,
  onFiles,
  onContracts,
  onObjects,
  onClients,
  onAgents,
  showOwnerControl,
  onSettings,
  recentItems,
  onRecent,
  onRename,
  onTogglePin,
  onDelete,
  user,
}: MobileNavigationDrawerProps) {
  const { t } = useLocale()
  const displayName = verifiedDisplayName(user) ?? t('settings.guest')
  const initials = verifiedInitials(user) ?? 'К'
  const ownerActions = [
    ...(showOwnerControl ? [{ label: t('drawer.agents'), icon: Bot, action: onAgents }] : []),
  ]
  const dialogRef = useRef<HTMLElement>(null)
  const returnFocusRef = useRef<HTMLElement | null>(null)

  useEffect(() => {
    if (!open) return
    returnFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const dialog = dialogRef.current
    const main = document.querySelector<HTMLElement>('.shell-main')
    const header = document.querySelector<HTMLElement>('.shell-mobile-header')
    main?.setAttribute('inert', '')
    header?.setAttribute('inert', '')
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    window.requestAnimationFrame(() => dialog?.querySelector<HTMLElement>('button')?.focus())
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
      if (event.key !== 'Tab' || !dialog) return
      const focusable = Array.from(dialog.querySelectorAll<HTMLElement>('button:not([disabled]), [tabindex]:not([tabindex="-1"])'))
      const first = focusable[0]
      const last = focusable.at(-1)
      if (!first || !last) return
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      main?.removeAttribute('inert')
      header?.removeAttribute('inert')
      document.body.style.overflow = previousOverflow
      returnFocusRef.current?.focus()
    }
  }, [onClose, open])

  return (
    <div
      className={`mobile-navigation-layer ${open ? 'is-open' : ''}`}
      aria-hidden={!open}
      data-scrim-state={open ? 'open' : 'closed'}
      inert={!open ? true : undefined}
    >
      <button
        type="button"
        className="mobile-navigation-backdrop"
        aria-label={t('shell.closeMenu')}
        aria-hidden={!open}
        tabIndex={open ? 0 : -1}
        onClick={onClose}
      />
      <aside ref={dialogRef} className={`mobile-navigation-drawer ${styles.drawer}`} role="dialog" aria-modal="true" aria-label={t('shell.navigation')} inert={!open ? true : undefined}>
        <header className={`mobile-navigation-header ${styles.header}`}>
          <strong>Kolibri</strong>
          <button type="button" aria-label={t('shell.closeMenu')} onClick={onClose}><X size={21} /></button>
        </header>

        <div className={`mobile-navigation-list ${styles.list}`}>
          <button type="button" className="is-primary" onClick={() => onNavigate(onNew)}>
            <SquarePen size={20} strokeWidth={1.8} />
            <span>{t('shell.newProject')}</span>
          </button>
          <button type="button" onClick={() => onNavigate(onSearch)}>
            <Search size={20} strokeWidth={1.8} />
            <span>{t('shell.search')}</span>
          </button>
          <button type="button" className={activePath === '/contracts' ? 'is-active' : undefined} aria-current={activePath === '/contracts' ? 'page' : undefined} onClick={() => onNavigate(onContracts)}>
            <FileSignature size={20} strokeWidth={1.8} />
            <span>{t('shell.contracts')}</span>
          </button>
          <button type="button" className={activePath === '/library' ? 'is-active' : undefined} aria-current={activePath === '/library' ? 'page' : undefined} onClick={() => onNavigate(onFiles)}>
            <FolderOpen size={20} strokeWidth={1.8} />
            <span>{t('shell.files')}</span>
          </button>
          <button type="button" className={activePath === '/objects' ? 'is-active' : undefined} aria-current={activePath === '/objects' ? 'page' : undefined} onClick={() => onNavigate(onObjects)}>
            <Building2 size={20} strokeWidth={1.8} />
            <span>Объекты</span>
          </button>
          <button type="button" className={activePath === '/clients' ? 'is-active' : undefined} aria-current={activePath === '/clients' ? 'page' : undefined} onClick={() => onNavigate(onClients)}>
            <UserRound size={20} strokeWidth={1.8} />
            <span>Заказчики</span>
          </button>
        </div>

        <section className={`mobile-navigation-recent ${styles.recent}`} aria-label={t('drawer.recentProjects')}>
          <div className={`mobile-navigation-section-title ${styles.sectionTitle}`}>
            <span>{t('shell.recent')}</span>
            <button type="button" onClick={() => onNavigate(onHistory)}>{t('drawer.all')}</button>
          </div>
          {recentItems.length ? recentItems.slice(0, 8).map(item => (
            <RecentProjectItem key={item.id} project={item} variant="drawer" onOpen={projectId => onNavigate(() => onRecent(projectId))} onRename={onRename} onTogglePin={onTogglePin} onDelete={onDelete} />
          )) : <p>{t('drawer.empty')}</p>}
        </section>
        <div className={`mobile-navigation-footer ${styles.footer}`}>
          {ownerActions.map(item => {
            const Icon = item.icon
            return (
              <button key={item.label} type="button" onClick={() => onNavigate(item.action)}>
                <Icon size={20} strokeWidth={1.8} />
                <span>{item.label}</span>
              </button>
            )
          })}
          <button type="button" className={`mobile-navigation-profile ${styles.profile}`} onClick={() => onNavigate(onSettings)}>
            <span className="mobile-navigation-avatar">{initials}</span>
            <span><strong>{displayName}</strong><small>{t('drawer.profileSettings')}</small></span>
            <Settings size={20} strokeWidth={1.8} />
          </button>
        </div>
      </aside>
    </div>
  )
}
