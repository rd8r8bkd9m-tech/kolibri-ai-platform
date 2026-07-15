import { useEffect, useRef } from 'react'
import { Bot, Search, Settings, SquarePen, X } from 'lucide-react'
import type { AuthUser, Project } from '@/lib/api'
import { useLocale } from '@/features/localization'
import { verifiedDisplayName, verifiedInitials } from '@/features/auth/shellIdentity'

interface MobileNavigationDrawerProps {
  open: boolean
  onClose: () => void
  onNavigate: (action: () => void) => void
  onNew: () => void
  onHistory: () => void
  onSearch: () => void
  onFiles: () => void
  onAgents: () => void
  showOwnerControl: boolean
  onSettings: () => void
  recentItems: Project[]
  onRecent: (projectId: string) => void
  user: AuthUser | null
}

export default function MobileNavigationDrawer({
  open,
  onClose,
  onNavigate,
  onNew,
  onHistory,
  onSearch,
  onAgents,
  showOwnerControl,
  onSettings,
  recentItems,
  onRecent,
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
    <div className={`mobile-navigation-layer ${open ? 'is-open' : ''}`} aria-hidden={!open}>
      <button type="button" className="mobile-navigation-backdrop" aria-label={t('shell.closeMenu')} tabIndex={open ? 0 : -1} onClick={onClose} />
      <aside ref={dialogRef} className="mobile-navigation-drawer" role="dialog" aria-modal="true" aria-label={t('shell.navigation')} inert={!open ? true : undefined}>
        <header className="mobile-navigation-header">
          <strong>Kolibri</strong>
          <button type="button" aria-label={t('shell.closeMenu')} onClick={onClose}><X size={21} /></button>
        </header>

        <div className="mobile-navigation-list">
          <button type="button" className="is-primary" onClick={() => onNavigate(onNew)}>
            <SquarePen size={20} strokeWidth={1.8} />
            <span>{t('shell.newProject')}</span>
          </button>
          <button type="button" onClick={() => onNavigate(onSearch)}>
            <Search size={20} strokeWidth={1.8} />
            <span>{t('shell.search')}</span>
          </button>
        </div>

        <section className="mobile-navigation-recent" aria-label={t('drawer.recentProjects')}>
          <div className="mobile-navigation-section-title">
            <span>{t('shell.recent')}</span>
            <button type="button" onClick={() => onNavigate(onHistory)}>{t('drawer.all')}</button>
          </div>
          {recentItems.length ? recentItems.slice(0, 30).map(item => (
            <button key={item.id} type="button" onClick={() => onNavigate(() => onRecent(item.id))}>{item.title}</button>
          )) : <p>{t('drawer.empty')}</p>}
        </section>
        <div className="mobile-navigation-footer">
          {ownerActions.map(item => {
            const Icon = item.icon
            return (
              <button key={item.label} type="button" onClick={() => onNavigate(item.action)}>
                <Icon size={20} strokeWidth={1.8} />
                <span>{item.label}</span>
              </button>
            )
          })}
          <button type="button" className="mobile-navigation-profile" onClick={() => onNavigate(onSettings)}>
            <span className="mobile-navigation-avatar">{initials}</span>
            <span><strong>{displayName}</strong><small>{t('drawer.profileSettings')}</small></span>
            <Settings size={20} strokeWidth={1.8} />
          </button>
        </div>
      </aside>
    </div>
  )
}
