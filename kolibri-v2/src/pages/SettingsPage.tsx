import { useState, useEffect, useCallback } from 'react'
import { User, Palette, Bell, Shield, Globe, Keyboard, LogOut } from 'lucide-react'
import { auth, type AuthUser } from '@/lib/api'
import { applyKolibriTheme, getStoredTheme, type KolibriTheme } from '@/features/shell/theme'
import { isSupportedLocale, useLocale, type TranslationKey } from '@/features/localization'

const tabs = [
  { id: 'profile', labelKey: 'settings.profile', icon: User },
  { id: 'appearance', labelKey: 'settings.appearance', icon: Palette },
  { id: 'notifications', labelKey: 'settings.notifications', icon: Bell },
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
      onClick={toggle}
      className={`relative w-10 h-6 rounded-full transition-colors ${on ? 'bg-[var(--accent-teal)]' : 'bg-[var(--border-subtle)]'}`}
    >
      <div className={`absolute top-0.5 w-5 h-5 bg-white rounded-full shadow-sm transition-transform ${on ? 'translate-x-4' : 'translate-x-0.5'}`} />
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
  const { locale, setLocale, t } = useLocale()
  const [activeTab, setActiveTab] = useState('profile')
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

  useEffect(() => {
    applyKolibriTheme(theme)
  }, [theme])

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

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-[800px] mx-auto px-4 sm:px-6 py-6">
        <h1 className="text-[22px] sm:text-[26px] font-semibold text-[var(--text-primary)] tracking-tight mb-6">{t('settings.title')}</h1>

        <div className="flex flex-col md:flex-row gap-6">
          {/* Sidebar */}
          <nav className="md:w-48 flex-shrink-0">
            <div className="flex md:flex-col gap-1 overflow-x-auto md:overflow-visible pb-2 md:pb-0">
              {tabs.map(tab => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`flex items-center gap-2.5 px-3 py-2 rounded-[var(--radius-md)] text-[13px] whitespace-nowrap transition-colors ${
                    activeTab === tab.id
                      ? 'bg-[var(--accent-teal)]/10 text-[var(--accent-teal)] font-medium'
                      : 'text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)]'
                  }`}
                >
                  <tab.icon size={16} strokeWidth={1.8} />
                  <span>{t(tab.labelKey)}</span>
                </button>
              ))}
            </div>
          </nav>

          {/* Content */}
          <div className="flex-1 min-w-0">
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
                    </div>
                  </div>
                </div>
                <div className="pb-4 border-b border-[var(--border-subtle)]">
                  <label className="block text-[12px] text-[var(--text-tertiary)] mb-1.5">{t('settings.name')}</label>
                  <input value={name} onChange={e => setName(e.target.value)} className="w-full h-9 px-3 bg-[var(--bg-secondary)] border border-[var(--border-subtle)] rounded-[var(--radius-md)] text-[13px] text-[var(--text-primary)] outline-none focus:border-[var(--accent-teal)] transition-colors" />
                </div>
                <div className="pb-4 border-b border-[var(--border-subtle)]">
                  <label className="block text-[12px] text-[var(--text-tertiary)] mb-1.5">Email</label>
                  <input value={email} onChange={e => setEmail(e.target.value)} type="email" className="w-full h-9 px-3 bg-[var(--bg-secondary)] border border-[var(--border-subtle)] rounded-[var(--radius-md)] text-[13px] text-[var(--text-primary)] outline-none focus:border-[var(--accent-teal)] transition-colors" />
                </div>
                <div className="flex items-center gap-3">
                  <button onClick={handleSaveProfile} disabled={saving} className="h-9 px-4 bg-[var(--accent-teal)] text-white rounded-[var(--radius-md)] text-[13px] font-medium hover:bg-[var(--accent-teal-hover)] transition-colors disabled:opacity-50">
                    {saving ? t('settings.saving') : t('settings.save')}
                  </button>
                  {saved && <span className="text-[13px] text-emerald-600">{t('settings.saved')}</span>}
                </div>
              </div>
            )}

            {activeTab === 'appearance' && (
              <div className="space-y-6">
                <h2 className="text-[16px] font-semibold text-[var(--text-primary)] mb-4">{t('settings.appearance')}</h2>
                <div>
                  <label className="block text-[12px] text-[var(--text-tertiary)] mb-2">{t('settings.theme')}</label>
                  <div className="grid grid-cols-3 gap-3">
                    {([['light', t('settings.themeLight')], ['dark', t('settings.themeDark')], ['system', t('settings.themeSystem')]] as const).map(([value, label]) => (
                      <button
                        key={value}
                        onClick={() => setTheme(value)}
                        className={`p-3 rounded-[var(--radius-lg)] border text-center text-[13px] transition-colors ${theme === value ? 'border-[var(--accent-teal)] bg-[var(--accent-teal)]/5 text-[var(--accent-teal)]' : 'border-[var(--border-subtle)] text-[var(--text-secondary)] hover:border-[var(--border-hover)]'}`}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                </div>
                <div>
                  <label className="block text-[12px] text-[var(--text-tertiary)] mb-2">{t('settings.accent')}</label>
                  <div className="flex gap-3">
                    {['#3ABAB4', '#9B8AF8', '#C2498C', '#3b82f6', '#10b981', '#f59e0b'].map(c => (
                      <button key={c} onClick={() => { setAccent(c); localStorage.setItem('kolibri-accent', c) }} className={`w-8 h-8 rounded-full transition-transform hover:scale-110 ${accent === c ? 'ring-2 ring-offset-2 ring-[var(--text-primary)]' : ''}`} style={{ background: c }} />
                    ))}
                  </div>
                </div>
                <div className="flex items-center justify-between py-3 border-b border-[var(--border-subtle)]">
                  <span className="text-[14px] text-[var(--text-primary)]">{t('settings.reduceMotion')}</span>
                  <Toggle storageKey="kolibri-reduce-motion" />
                </div>
              </div>
            )}

            {activeTab === 'notifications' && (
              <div className="space-y-4">
                <h2 className="text-[16px] font-semibold text-[var(--text-primary)] mb-4">{t('settings.notifications')}</h2>
                {[
                  { label: t('settings.push'), desc: t('settings.pushDescription'), key: 'notif-push' },
                  { label: t('settings.emailNotifications'), desc: t('settings.emailNotificationsDescription'), key: 'notif-email' },
                  { label: t('settings.agentNotifications'), desc: t('settings.agentNotificationsDescription'), key: 'notif-agents' },
                  { label: t('settings.serverNotifications'), desc: t('settings.serverNotificationsDescription'), key: 'notif-servers' },
                  { label: t('settings.sound'), desc: t('settings.soundDescription'), key: 'notif-sound' },
                ].map(n => (
                  <div key={n.label} className="flex items-center justify-between py-2">
                    <div>
                      <p className="text-[14px] text-[var(--text-primary)]">{n.label}</p>
                      <p className="text-[12px] text-[var(--text-tertiary)]">{n.desc}</p>
                    </div>
                    <Toggle storageKey={n.key} defaultOn />
                  </div>
                ))}
              </div>
            )}

            {activeTab === 'security' && (
              <div className="space-y-6">
                <h2 className="text-[16px] font-semibold text-[var(--text-primary)] mb-4">{t('settings.security')}</h2>
                <div className="p-4 rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-secondary)]">
                  <p className="text-[14px] font-medium text-[var(--text-primary)] mb-3">{t('settings.changePassword')}</p>
                  <div className="space-y-3">
                    <input type="password" value={currentPassword} onChange={e => setCurrentPassword(e.target.value)} placeholder={t('settings.currentPassword')} className="w-full h-9 px-3 bg-[var(--bg-input)] text-[var(--text-primary)] border border-[var(--border-subtle)] rounded-[var(--radius-md)] text-[13px] outline-none focus:border-[var(--accent-teal)]" />
                    <input type="password" value={newPassword} onChange={e => setNewPassword(e.target.value)} placeholder={t('settings.newPassword')} className="w-full h-9 px-3 bg-[var(--bg-input)] text-[var(--text-primary)] border border-[var(--border-subtle)] rounded-[var(--radius-md)] text-[13px] outline-none focus:border-[var(--accent-teal)]" />
                    {passwordError && <p className="text-[12px] text-red-500">{passwordError}</p>}
                    {passwordSaved && <p className="text-[12px] text-emerald-600">{t('settings.passwordChanged')}</p>}
                    <button onClick={handleChangePassword} className="h-8 px-3 rounded-[var(--radius-md)] border border-[var(--border-subtle)] text-[13px] text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] transition-colors">{t('settings.changePasswordAction')}</button>
                  </div>
                </div>
                <div className="p-4 rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-secondary)]">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-[14px] font-medium text-[var(--text-primary)] mb-1">{t('settings.twoFactor')}</p>
                      <p className="text-[12px] text-[var(--text-tertiary)]">{t('settings.twoFactorDescription')}</p>
                    </div>
                    <Toggle storageKey="kolibri-2fa" />
                  </div>
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
                  { action: t('settings.shortcutNewChat'), key: 'Ctrl + K' },
                  { action: t('settings.shortcutSearch'), key: 'Ctrl + /' },
                  { action: t('settings.shortcutSend'), key: 'Enter' },
                  { action: t('settings.shortcutNewLine'), key: 'Shift + Enter' },
                  { action: t('settings.shortcutLibrary'), key: 'Ctrl + L' },
                  { action: t('settings.shortcutSettings'), key: 'Ctrl + ,' },
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
