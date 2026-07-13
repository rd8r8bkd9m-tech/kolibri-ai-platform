import type { ReactNode } from 'react'
import { NavLink } from 'react-router'
import { useLocale } from '@/features/localization'

interface DeveloperFrameProps {
  title: string
  copy: string
  children: ReactNode
}

const navigation = [
  { to: '/developers', label: 'developer.overview', end: true },
  { to: '/docs', label: 'developer.docs', end: false },
  { to: '/playground', label: 'developer.playground', end: false },
] as const

export default function DeveloperFrame({ title, copy, children }: DeveloperFrameProps) {
  const { t } = useLocale()

  return (
    <section className="developer-surface">
      <div className="developer-frame">
        <header className="developer-heading">
          <p className="developer-eyebrow">{t('developer.eyebrow')}</p>
          <h1>{title}</h1>
          <p>{copy}</p>
        </header>

        <nav className="developer-tabs" aria-label={t('developer.eyebrow')}>
          {navigation.map(item => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) => `developer-tab ${isActive ? 'is-active' : ''}`}
            >
              {t(item.label)}
            </NavLink>
          ))}
        </nav>

        {children}
      </div>
    </section>
  )
}
