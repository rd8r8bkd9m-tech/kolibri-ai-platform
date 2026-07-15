import { useEffect, useRef, type ComponentType } from 'react'
import { Bot, Files, Plus, Search, Settings, X } from 'lucide-react'
import CartoonMascot from '@/components/CartoonMascot'
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

export default function MobileNavigationDrawer({ open, onClose, onNavigate, onNew, onHistory, onSearch, onFiles, onAgents, showOwnerControl, onSettings, recentItems, onRecent, user }: MobileNavigationDrawerProps) {
  const { t } = useLocale()
  const displayName = verifiedDisplayName(user) ?? t('settings.guest')
  const initials = verifiedInitials(user) ?? 'К'
  const dialogRef = useRef<HTMLElement>(null)
  const returnFocusRef = useRef<HTMLElement | null>(null)
  const actions: Array<{ label: string; icon: ComponentType<{ size?: number; strokeWidth?: number }>; action: () => void }> = [
    { label: t('shell.newProject'), icon: Plus, action: onNew },
    { label: t('drawer.searchProjects'), icon: Search, action: onSearch },
    { label: t('drawer.library'), icon: Files, action: onFiles },
    ...(showOwnerControl ? [{ label: t('drawer.agents'), icon: Bot, action: onAgents }] : []),
  ]

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
    <div className={`mobile-navigation-layer md:hidden ${open ? 'is-open' : ''}`} aria-hidden={!open}>
      <button type="button" className="mobile-navigation-backdrop" aria-label={t('shell.closeMenu')} tabIndex={open ? 0 : -1} onClick={onClose} />
      <aside ref={dialogRef} className="mobile-navigation-drawer" role="dialog" aria-modal="true" aria-label={t('shell.navigation')} inert={!open ? true : undefined}>
        <header className="mobile-navigation-header">
          <CartoonMascot size={44} />
          <div><strong>Kolibri</strong></div>
          <button type="button" aria-label={t('shell.closeMenu')} onClick={onClose}><X size={23} /></button>
        </header>
        <nav className="mobile-navigation-list" aria-label={t('drawer.mainNavigation')}>
          {actions.map(({ label, icon: Icon, action }) => (
            <button key={label} type="button" className={action === onNew ? 'is-primary' : ''} onClick={() => onNavigate(action)}>
              <Icon size={22} strokeWidth={1.8} />
              <span>{label}</span>
            </button>
          ))}
        </nav>
        <section className="mobile-navigation-recent" aria-label={t('drawer.recentProjects')}>
          <div className="mobile-navigation-section-title"><span>{t('shell.recent')}</span><button type="button" onClick={() => onNavigate(onHistory)}>{t('drawer.all')}</button></div>
          {recentItems.length ? recentItems.slice(0, 8).map(item => (
            <button key={item.id} type="button" onClick={() => onNavigate(() => onRecent(item.id))}>{item.title}</button>
          )) : <p>{t('drawer.empty')}</p>}
        </section>
        <button type="button" className="mobile-navigation-profile" onClick={() => onNavigate(onSettings)}>
          <span className="mobile-navigation-avatar">{initials}</span>
          <span><strong>{displayName}</strong><small>{t('drawer.profileSettings')}</small></span>
          <Settings size={23} strokeWidth={1.8} />
        </button>
      </aside>
    </div>
  )
}
