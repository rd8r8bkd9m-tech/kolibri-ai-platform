import { useState } from 'react'
import { User, Palette, Bell, Shield, Globe, Keyboard, ChevronRight } from 'lucide-react'

const tabs = [
  { id: 'profile', label: 'Профиль', icon: User },
  { id: 'appearance', label: 'Внешний вид', icon: Palette },
  { id: 'notifications', label: 'Уведомления', icon: Bell },
  { id: 'security', label: 'Безопасность', icon: Shield },
  { id: 'language', label: 'Язык', icon: Globe },
  { id: 'shortcuts', label: 'Горячие клавиши', icon: Keyboard },
]

function Toggle({ defaultOn = false }: { defaultOn?: boolean }) {
  const [on, setOn] = useState(defaultOn)
  return (
    <button
      onClick={() => setOn(!on)}
      className={`relative w-10 h-6 rounded-full transition-colors ${on ? 'bg-[var(--accent-teal)]' : 'bg-[var(--border-subtle)]'}`}
    >
      <div className={`absolute top-0.5 w-5 h-5 bg-white rounded-full shadow-sm transition-transform ${on ? 'translate-x-4' : 'translate-x-0.5'}`} />
    </button>
  )
}

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState('profile')

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-[800px] mx-auto px-4 sm:px-6 py-6">
        <h1 className="text-[22px] sm:text-[26px] font-semibold text-[var(--text-primary)] tracking-tight mb-6">Настройки</h1>

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
                  <span>{tab.label}</span>
                </button>
              ))}
            </div>
          </nav>

          {/* Content */}
          <div className="flex-1 min-w-0">
            {activeTab === 'profile' && (
              <div className="space-y-6">
                <div>
                  <h2 className="text-[16px] font-semibold text-[var(--text-primary)] mb-4">Профиль</h2>
                  <div className="flex items-center gap-4 mb-6">
                    <div className="w-16 h-16 rounded-full bg-[var(--accent-teal)]/10 flex items-center justify-center">
                      <User size={24} className="text-[var(--accent-teal)]" strokeWidth={1.5} />
                    </div>
                    <div>
                      <p className="text-[14px] font-medium text-[var(--text-primary)]">Администратор</p>
                      <p className="text-[12px] text-[var(--text-tertiary)]">admin@kolibri.dev</p>
                    </div>
                  </div>
                </div>
                {[
                  { label: 'Имя', value: 'Администратор' },
                  { label: 'Email', value: 'admin@kolibri.dev' },
                  { label: 'Компания', value: 'ООО Колибри' },
                  { label: 'Должность', value: 'Руководитель проекта' },
                ].map(field => (
                  <div key={field.label} className="pb-4 border-b border-[var(--border-subtle)]">
                    <label className="block text-[12px] text-[var(--text-tertiary)] mb-1.5">{field.label}</label>
                    <input defaultValue={field.value} className="w-full h-9 px-3 bg-[var(--bg-secondary)] border border-[var(--border-subtle)] rounded-[var(--radius-md)] text-[13px] text-[var(--text-primary)] outline-none focus:border-[var(--accent-teal)] transition-colors" />
                  </div>
                ))}
                <button className="h-9 px-4 bg-[var(--accent-teal)] text-white rounded-[var(--radius-md)] text-[13px] font-medium hover:bg-[var(--accent-teal-hover)] transition-colors">
                  Сохранить
                </button>
              </div>
            )}

            {activeTab === 'appearance' && (
              <div className="space-y-6">
                <h2 className="text-[16px] font-semibold text-[var(--text-primary)] mb-4">Внешний вид</h2>
                <div>
                  <label className="block text-[12px] text-[var(--text-tertiary)] mb-2">Тема</label>
                  <div className="grid grid-cols-3 gap-3">
                    {['Светлая', 'Тёмная', 'Системная'].map(t => (
                      <button key={t} className={`p-3 rounded-[var(--radius-lg)] border text-center text-[13px] transition-colors ${t === 'Светлая' ? 'border-[var(--accent-teal)] bg-[var(--accent-teal)]/5 text-[var(--accent-teal)]' : 'border-[var(--border-subtle)] text-[var(--text-secondary)] hover:border-[var(--border-hover)]'}`}>
                        {t}
                      </button>
                    ))}
                  </div>
                </div>
                <div>
                  <label className="block text-[12px] text-[var(--text-tertiary)] mb-2">Акцентный цвет</label>
                  <div className="flex gap-3">
                    {['#3ABAB4', '#9B8AF8', '#C2498C', '#3b82f6', '#10b981', '#f59e0b'].map(c => (
                      <button key={c} className="w-8 h-8 rounded-full transition-transform hover:scale-110" style={{ background: c }} />
                    ))}
                  </div>
                </div>
                <div className="flex items-center justify-between py-3 border-b border-[var(--border-subtle)]">
                  <span className="text-[14px] text-[var(--text-primary)]">Уменьшить движение</span>
                  <Toggle />
                </div>
              </div>
            )}

            {activeTab === 'notifications' && (
              <div className="space-y-4">
                <h2 className="text-[16px] font-semibold text-[var(--text-primary)] mb-4">Уведомления</h2>
                {[
                  { label: 'Push-уведомления', desc: 'Всплывающие уведомления в браузере' },
                  { label: 'Email-уведомления', desc: 'Письма о важных событиях' },
                  { label: 'Уведомления об агентах', desc: 'Статус агентов и задач' },
                  { label: 'Уведомления о серверах', desc: 'Проблемы с нодами' },
                  { label: 'Звуковые сигналы', desc: 'Звук при новых сообщениях' },
                ].map(n => (
                  <div key={n.label} className="flex items-center justify-between py-2">
                    <div>
                      <p className="text-[14px] text-[var(--text-primary)]">{n.label}</p>
                      <p className="text-[12px] text-[var(--text-tertiary)]">{n.desc}</p>
                    </div>
                    <Toggle defaultOn />
                  </div>
                ))}
              </div>
            )}

            {activeTab === 'security' && (
              <div className="space-y-6">
                <h2 className="text-[16px] font-semibold text-[var(--text-primary)] mb-4">Безопасность</h2>
                <div className="p-4 rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-secondary)]">
                  <p className="text-[14px] font-medium text-[var(--text-primary)] mb-1">Пароль</p>
                  <p className="text-[12px] text-[var(--text-tertiary)] mb-3">Последнее изменение: 15 июня 2026</p>
                  <button className="h-8 px-3 rounded-[var(--radius-md)] border border-[var(--border-subtle)] text-[13px] text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] transition-colors">Изменить пароль</button>
                </div>
                <div className="p-4 rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-secondary)]">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-[14px] font-medium text-[var(--text-primary)] mb-1">Двухфакторная аутентификация</p>
                      <p className="text-[12px] text-[var(--text-tertiary)]">Защитите аккаунт дополнительным кодом</p>
                    </div>
                    <Toggle />
                  </div>
                </div>
                <div>
                  <p className="text-[14px] font-medium text-[var(--text-primary)] mb-2">Сессии</p>
                  {[
                    { device: 'MacBook Pro', location: 'Москва', current: true },
                    { device: 'iPhone 15', location: 'Москва', current: false },
                  ].map(s => (
                    <div key={s.device} className="flex items-center justify-between py-2 border-b border-[var(--border-subtle)]">
                      <div>
                        <p className="text-[13px] text-[var(--text-primary)]">{s.device} {s.current && <span className="text-[10px] text-[var(--accent-teal)] bg-[var(--accent-teal)]/10 px-1.5 py-0.5 rounded-full ml-1">Текущая</span>}</p>
                        <p className="text-[11px] text-[var(--text-tertiary)]">{s.location}</p>
                      </div>
                      {!s.current && <button className="text-[12px] text-red-500 hover:text-red-600 transition-colors">Завершить</button>}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {activeTab === 'language' && (
              <div className="space-y-6">
                <h2 className="text-[16px] font-semibold text-[var(--text-primary)] mb-4">Язык и регион</h2>
                <div className="pb-4 border-b border-[var(--border-subtle)]">
                  <label className="block text-[12px] text-[var(--text-tertiary)] mb-1.5">Язык интерфейса</label>
                  <select className="w-full h-9 px-3 bg-[var(--bg-secondary)] border border-[var(--border-subtle)] rounded-[var(--radius-md)] text-[13px] text-[var(--text-primary)] outline-none">
                    <option>Русский</option>
                    <option>English</option>
                  </select>
                </div>
                <div className="pb-4 border-b border-[var(--border-subtle)]">
                  <label className="block text-[12px] text-[var(--text-tertiary)] mb-1.5">Формат даты</label>
                  <select className="w-full h-9 px-3 bg-[var(--bg-secondary)] border border-[var(--border-subtle)] rounded-[var(--radius-md)] text-[13px] text-[var(--text-primary)] outline-none">
                    <option>DD.MM.YYYY</option>
                    <option>MM/DD/YYYY</option>
                    <option>YYYY-MM-DD</option>
                  </select>
                </div>
                <div>
                  <label className="block text-[12px] text-[var(--text-tertiary)] mb-1.5">Валюта</label>
                  <select className="w-full h-9 px-3 bg-[var(--bg-secondary)] border border-[var(--border-subtle)] rounded-[var(--radius-md)] text-[13px] text-[var(--text-primary)] outline-none">
                    <option>RUB (₽)</option>
                    <option>USD ($)</option>
                    <option>EUR (€)</option>
                  </select>
                </div>
              </div>
            )}

            {activeTab === 'shortcuts' && (
              <div className="space-y-4">
                <h2 className="text-[16px] font-semibold text-[var(--text-primary)] mb-4">Горячие клавиши</h2>
                {[
                  { action: 'Новый чат', key: 'Ctrl + K' },
                  { action: 'Поиск', key: 'Ctrl + /' },
                  { action: 'Отправить сообщение', key: 'Enter' },
                  { action: 'Новая строка', key: 'Shift + Enter' },
                  { action: 'Библиотека', key: 'Ctrl + L' },
                  { action: 'Настройки', key: 'Ctrl + ,' },
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
