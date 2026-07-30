import { useState, useEffect, useCallback } from 'react'
import { User, Palette, Shield, Globe, Keyboard, LogOut, Code2, Factory, Building2, WalletCards, Cpu } from 'lucide-react'
import { Link, useSearchParams } from 'react-router'
import { auth, organizations, type AuthUser, type OrganizationSummary } from '@/lib/api'
import { applyKolibriTheme, getStoredTheme, type KolibriTheme } from '@/features/shell/theme'
import { isSupportedLocale, useLocale, type TranslationKey } from '@/features/localization'
import OwnerBuildDiagnostics from '@/features/shell/OwnerBuildDiagnostics'
import { isOwnerRole } from '@/features/shell/releaseIdentity'
import OrganizationSettings from '@/features/organizations/OrganizationSettings'
import BillingSettings from '@/features/billing/BillingSettings'
import OwnerModelConnections from '@/features/settings/OwnerModelConnections'

const tabs = [
  { id: 'profile', labelKey: 'settings.profile', icon: User },
  { id: 'organization', labelKey: 'settings.organization', icon: Building2 },
  { id: 'billing', labelKey: 'settings.billing', icon: WalletCards },
  { id: 'models', labelKey: 'settings.models', icon: Cpu },
  { id: 'appearance', labelKey: 'settings.appearance', icon: Palette },
  { id: 'security', labelKey: 'settings.security', icon: Shield },
  { id: 'language', labelKey: 'settings.language', icon: Globe },
  { id: 'shortcuts', labelKey: 'settings.shortcuts', icon: Keyboard },
] satisfies Array<{ id: string; labelKey: TranslationKey; icon: typeof User }>

function Toggle({ storageKey, defaultOn = false }: { storageKey?: string; defaultOn?: boolean }) {
  const [on, setOn] = useState(() => {
    if (storageKey) {
      const saved = localStorage.getItem(storageKey)
      if (saved !== null) return saved === 'true'
    }
    return defaultOn
  })

  const toggle = useCallback(() => {
    setOn(prev => {
      const next = !prev
      if (storageKey) localStorage.setItem(storageKey, String(next))
      return next
    })
  }, [storageKey])

  return (
    <button
      type="button"
      onClick={toggle}
      aria-pressed={on}
      aria-label="Переключить настройку"
      className={`settings-native-toggle ${on ? 'is-on' : ''}`}
    >
      <span aria-hidden="true" />
    </button>
  )
}

interface SettingsPageProps {
  user?: AuthUser | null
  onLogout?: () => void
}

export default function SettingsPage({ user, onLogout }: SettingsPageProps) {
  return <SettingsPageContent key={user?.id ?? 'guest'} user={user} onLogout={onLogout} />
}

function SettingsPageContent({ user, onLogout }: SettingsPageProps) {
  const [searchParams] = useSearchParams()
  const { locale, setLocale, t } = useLocale()
  const [activeTab, setActiveTab] = useState(() => searchParams.get('section') || 'profile')
  const [name, setName] = useState(user?.name || '')
  const [email, setEmail] = useState(user?.email || '')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [passwordError, setPasswordError] = useState('')
  const [passwordSaved, setPasswordSaved] = useState(false)
  const [theme, setTheme] = useState<KolibriTheme>(getStoredTheme)
  const [accent, setAccent] = useState(() => localStorage.getItem('kolibri-accent') || '#3ABAB4')
  const [dateFormat, setDateFormat] = useState(() => localStorage.getItem('kolibri-date-format') || 'DD.MM.YYYY')
  const [currency, setCurrency] = useState(() => localStorage.getItem('kolibri-currency') || 'RUB')
  const [organizationItems, setOrganizationItems] = useState<OrganizationSummary[]>([])
  const [organizationsLoading, setOrganizationsLoading] = useState(Boolean(user))
  const [organizationsError, setOrganizationsError] = useState(false)

  const loadOrganizations = useCallback(async () => {
    if (!user) {
      setOrganizationItems([])
      setOrganizationsLoading(false)
      setOrganizationsError(false)
      return
    }
    setOrganizationsLoading(true)
    setOrganizationsError(false)
    try {
      const payload = await organizations.list()
      setOrganizationItems(payload.items)
    } catch {
      setOrganizationItems([])
      setOrganizationsError(true)
    } finally {
      setOrganizationsLoading(false)
    }
  }, [user])

  const activeOrganization = organizationItems.find(item => item.selected) ?? null

  useEffect(() => {
    applyKolibriTheme(theme)
  }, [theme])

  useEffect(() => {
    const initial = window.setTimeout(() => { void loadOrganizations() }, 0)
    return () => window.clearTimeout(initial)
  }, [loadOrganizations])

  useEffect(() => {
    document.documentElement.style.setProperty('--accent-teal', accent)
  }, [accent])

  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const handler = () => { if (theme === 'system') applyKolibriTheme('system', false) }
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [theme])

  const handleSaveProfile = async () => {
    if (!user) return
    setSaving(true)
    setSaved(false)
    try {
      await auth.updateMe({ name, email })
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (e) {
      console.error('Failed to save profile', e)
    } finally {
      setSaving(false)
    }
  }

  const handleChangePassword = async () => {
    setPasswordError('')
    setPasswordSaved(false)
    if (!currentPassword || !newPassword) {
      setPasswordError(t('settings.fillBoth'))
      return
    }
    if (newPassword.length < 6) {
      setPasswordError(t('settings.minSix'))
      return
    }
    try {
      await auth.updateMe({ current_password: currentPassword, new_password: newPassword })
      setPasswordSaved(true)
      setCurrentPassword('')
      setNewPassword('')
      setTimeout(() => setPasswordSaved(false), 2000)
    } catch {
      setPasswordError(t('settings.wrongPassword'))
    }
  }

  const visibleTabs = tabs.filter(tab => {
    if (tab.id === 'models') return isOwnerRole(user?.role)
    return !['security', 'organization', 'billing'].includes(tab.id) || Boolean(user)
  })
  const activeTabLabel = visibleTabs.find(tab => tab.id === activeTab)

  return (
    <div className="settings-page">
      <div className="settings-frame">
        <header className="settings-page-heading">
          <h1>{t('settings.title')}</h1>
          <span>{activeTabLabel ? t(activeTabLabel.labelKey) : t('settings.profile')}</span>
        </header>

        <div className="settings-layout">
          {/* Sidebar */}
          <nav className="settings-navigation" aria-label="Разделы настроек">
            <label className="settings-mobile-section-picker">
              <span>Раздел настроек</span>
              <select value={activeTab} onChange={event => setActiveTab(event.target.value)}>
                {visibleTabs.map(tab => <option key={tab.id} value={tab.id}>{t(tab.labelKey)}</option>)}
              </select>
            </label>
            <div>
              {visibleTabs.map(tab => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={activeTab === tab.id ? 'is-active' : undefined}
                  aria-current={activeTab === tab.id ? 'page' : undefined}
                >
                  <tab.icon size={16} strokeWidth={1.8} />
                  <span>{t(tab.labelKey)}</span>
                </button>
              ))}
            </div>
          </nav>

          {/* Content */}
          <div className="settings-content">
            {activeTab === 'models' && isOwnerRole(user?.role) && <OwnerModelConnections />}
            {activeTab === 'profile' && (
              <div className="space-y-6">
                <div>
                  <h2 className="text-[16px] font-semibold text-[var(--text-primary)] mb-4">{t('settings.profile')}</h2>
                  <div className="flex items-center gap-4 mb-6">
                    <div className="w-16 h-16 rounded-full bg-[var(--accent-teal)]/10 flex items-center justify-center">
                      <User size={24} className="text-[var(--accent-teal)]" strokeWidth={1.5} />
                    </div>
                    <div>
                      <p className="text-[14px] font-medium text-[var(--text-primary)]">{user?.name || t('settings.guest')}</p>
                      <p className="text-[12px] text-[var(--text-tertiary)]">{user?.email || t('settings.unauthorized')}</p>
                      {activeOrganization && (
                        <p className="mt-1 flex items-center gap-1.5 text-[11px] text-[var(--text-tertiary)]" data-active-organization>
                          <Building2 size={12} strokeWidth={1.7} aria-hidden="true" />
                          <span className="max-w-52 truncate">{activeOrganization.name}</span>
                        </p>
                      )}
                    </div>
                  </div>
                </div>
                {user ? <>
                  <div className="pb-4 border-b border-[var(--border-subtle)]">
                    <label className="block text-[12px] text-[var(--text-tertiary)] mb-1.5">{t('settings.name')}</label>
                    <input value={name} onChange={e => setName(e.target.value)} autoComplete="name" className="w-full h-9 px-3 bg-[var(--bg-secondary)] border border-[var(--border-subtle)] rounded-[var(--radius-md)] text-[13px] text-[var(--text-primary)] outline-none focus:border-[var(--accent-teal)] transition-colors" />
                  </div>
                  <div className="pb-4 border-b border-[var(--border-subtle)]">
                    <label className="block text-[12px] text-[var(--text-tertiary)] mb-1.5">Email</label>
                    <input value={email} onChange={e => setEmail(e.target.value)} type="email" autoComplete="email" className="w-full h-9 px-3 bg-[var(--bg-secondary)] border border-[var(--border-subtle)] rounded-[var(--radius-md)] text-[13px] text-[var(--text-primary)] outline-none focus:border-[var(--accent-teal)] transition-colors" />
                  </div>
                  <div className="flex items-center gap-3">
                    <button onClick={handleSaveProfile} disabled={saving} className="h-9 px-4 bg-[var(--accent-teal)] text-white rounded-[var(--radius-md)] text-[13px] font-medium hover:bg-[var(--accent-teal-hover)] transition-colors disabled:opacity-50">
                      {saving ? t('settings.saving') : t('settings.save')}
                    </button>
                    {saved && <span className="text-[13px] text-emerald-600">{t('settings.saved')}</span>}
                  </div>
                </> : <Link to="/login" className="inline-flex min-h-11 items-center rounded-[var(--radius-md)] bg-[var(--accent-teal)] px-4 text-[13px] font-medium text-white">
                  {t('developer.signIn')}
                </Link>}
                {isOwnerRole(user?.role) && <OwnerBuildDiagnostics />}
                {isOwnerRole(user?.role) && (
                  <Link
                    to="/control"
                    className="inline-flex min-h-11 items-center gap-2 rounded-[var(--radius-md)] bg-[var(--text-primary)] px-4 text-[13px] font-medium text-[var(--bg-primary)] transition-opacity hover:opacity-85"
                  >
                    <Factory size={16} aria-hidden="true" />
                    Управление фабрикой
                  </Link>
                )}
                <Link
                  to="/developers"
                  className="inline-flex min-h-11 items-center gap-2 rounded-[var(--radius-md)] border border-[var(--border-subtle)] px-4 text-[13px] font-medium text-[var(--text-secondary)] transition-colors hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)]"
                >
                  <Code2 size={16} aria-hidden="true" />
                  {t('settings.developerPortal')}
                </Link>
              </div>
            )}

            {activeTab === 'organization' && user && (
              <OrganizationSettings
                userId={user.id}
                items={organizationItems}
                loading={organizationsLoading}
                listError={organizationsError}
                onRefresh={loadOrganizations}
              />
            )}

            {activeTab === 'billing' && user && <BillingSettings />}

            {activeTab === 'appearance' && (
              <div className="settings-appearance-native">
                <h2>{t('settings.appearance')}</h2>
                <div className="settings-native-group">
                  <label className="settings-native-row">
                    <span><strong>{t('settings.theme')}</strong><small>{theme === 'light' ? t('settings.themeLight') : theme === 'dark' ? t('settings.themeDark') : t('settings.themeSystem')}</small></span>
                    <select value={theme} onChange={event => setTheme(event.target.value as KolibriTheme)} aria-label={t('settings.theme')}>
                      <option value="light">{t('settings.themeLight')}</option>
                      <option value="dark">{t('settings.themeDark')}</option>
                      <option value="system">{t('settings.themeSystem')}</option>
                    </select>
                  </label>
                  <div className="settings-native-color-row">
                    <span><strong>{t('settings.accent')}</strong><small>Цвет активных элементов</small></span>
                    <div className="settings-accent-options">
                    {['#3ABAB4', '#9B8AF8', '#C2498C', '#3b82f6', '#10b981', '#f59e0b'].map(c => (
                      <button type="button" key={c} aria-label={`Выбрать акцент ${c}`} aria-pressed={accent === c} onClick={() => { setAccent(c); localStorage.setItem('kolibri-accent', c) }} style={{ background: c }} />
                    ))}
                    </div>
                  </div>
                  <div className="settings-native-row">
                    <span><strong>{t('settings.reduceMotion')}</strong><small>Отключает лишние переходы и анимации</small></span>
                    <Toggle storageKey="kolibri-reduce-motion" />
                  </div>
                </div>
              </div>
            )}

            {activeTab === 'security' && (
              <div className="space-y-6">
                <h2 className="text-[16px] font-semibold text-[var(--text-primary)] mb-4">{t('settings.security')}</h2>
                <div className="p-4 rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-secondary)]">
                  <p className="text-[14px] font-medium text-[var(--text-primary)] mb-3">{t('settings.changePassword')}</p>
                  <form className="space-y-3" onSubmit={event => { event.preventDefault(); void handleChangePassword() }}>
                    <input type="password" autoComplete="current-password" value={currentPassword} onChange={e => setCurrentPassword(e.target.value)} placeholder={t('settings.currentPassword')} className="w-full h-9 px-3 bg-[var(--bg-input)] text-[var(--text-primary)] border border-[var(--border-subtle)] rounded-[var(--radius-md)] text-[13px] outline-none focus:border-[var(--accent-teal)]" />
                    <input type="password" autoComplete="new-password" value={newPassword} onChange={e => setNewPassword(e.target.value)} placeholder={t('settings.newPassword')} className="w-full h-9 px-3 bg-[var(--bg-input)] text-[var(--text-primary)] border border-[var(--border-subtle)] rounded-[var(--radius-md)] text-[13px] outline-none focus:border-[var(--accent-teal)]" />
                    {passwordError && <p className="text-[12px] text-red-500">{passwordError}</p>}
                    {passwordSaved && <p className="text-[12px] text-emerald-600">{t('settings.passwordChanged')}</p>}
                    <button type="submit" className="h-8 px-3 rounded-[var(--radius-md)] border border-[var(--border-subtle)] text-[13px] text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] transition-colors">{t('settings.changePasswordAction')}</button>
                  </form>
                </div>
                {user && (
                  <div className="p-4 rounded-[var(--radius-lg)] border border-red-200 bg-red-50">
                    <p className="text-[14px] font-medium text-red-700 mb-2">{t('settings.signOutSection')}</p>
                    <button onClick={onLogout} className="h-8 px-3 rounded-[var(--radius-md)] bg-red-500 text-white text-[13px] font-medium hover:bg-red-600 transition-colors flex items-center gap-1.5">
                      <LogOut size={14} /> {t('settings.signOut')}
                    </button>
                  </div>
                )}
              </div>
            )}

            {activeTab === 'language' && (
              <div className="space-y-6">
                <h2 className="text-[16px] font-semibold text-[var(--text-primary)] mb-4">{t('settings.languageRegion')}</h2>
                <div className="pb-4 border-b border-[var(--border-subtle)]">
                  <label className="block text-[12px] text-[var(--text-tertiary)] mb-1.5">{t('settings.interfaceLanguage')}</label>
                  <select value={locale} onChange={event => { if (isSupportedLocale(event.target.value)) setLocale(event.target.value) }} className="w-full h-9 px-3 bg-[var(--bg-secondary)] border border-[var(--border-subtle)] rounded-[var(--radius-md)] text-[13px] text-[var(--text-primary)] outline-none">
                    <option value="ru">{t('settings.russian')}</option>
                    <option value="en">{t('settings.english')}</option>
                  </select>
                </div>
                <div className="pb-4 border-b border-[var(--border-subtle)]">
                  <label className="block text-[12px] text-[var(--text-tertiary)] mb-1.5">{t('settings.dateFormat')}</label>
                  <select value={dateFormat} onChange={e => { setDateFormat(e.target.value); localStorage.setItem('kolibri-date-format', e.target.value) }} className="w-full h-9 px-3 bg-[var(--bg-secondary)] border border-[var(--border-subtle)] rounded-[var(--radius-md)] text-[13px] text-[var(--text-primary)] outline-none">
                    <option>DD.MM.YYYY</option>
                    <option>MM/DD/YYYY</option>
                    <option>YYYY-MM-DD</option>
                  </select>
                </div>
                <div>
                  <label className="block text-[12px] text-[var(--text-tertiary)] mb-1.5">{t('settings.currency')}</label>
                  <select value={currency} onChange={e => { setCurrency(e.target.value); localStorage.setItem('kolibri-currency', e.target.value) }} className="w-full h-9 px-3 bg-[var(--bg-secondary)] border border-[var(--border-subtle)] rounded-[var(--radius-md)] text-[13px] text-[var(--text-primary)] outline-none">
                    <option value="RUB">RUB (₽)</option>
                    <option value="USD">USD ($)</option>
                    <option value="EUR">EUR (€)</option>
                  </select>
                </div>
              </div>
            )}

            {activeTab === 'shortcuts' && (
              <div className="space-y-4">
                <h2 className="text-[16px] font-semibold text-[var(--text-primary)] mb-4">{t('settings.shortcuts')}</h2>
                {[
                  { action: t('settings.shortcutSearch'), key: 'Ctrl / ⌘ + K' },
                  { action: t('settings.shortcutSend'), key: 'Enter' },
                  { action: t('settings.shortcutNewLine'), key: 'Shift + Enter' },
                ].map(s => (
                  <div key={s.action} className="flex items-center justify-between py-2 border-b border-[var(--border-subtle)]">
                    <span className="text-[14px] text-[var(--text-primary)]">{s.action}</span>
                    <kbd className="px-2 py-1 bg-[var(--bg-elevated)] rounded-[var(--radius-sm)] text-[11px] font-mono text-[var(--text-secondary)]">{s.key}</kbd>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
