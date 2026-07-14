import { useEffect, useState } from 'react'
import { Outlet } from 'react-router'
import { useLocale } from '@/features/localization'
import { shell } from '@/lib/api'

type BootstrapState = 'loading' | 'ready' | 'error'

export default function ShellBootstrapBoundary() {
  const { t } = useLocale()
  const [attempt, setAttempt] = useState(0)
  const [state, setState] = useState<BootstrapState>('loading')

  useEffect(() => {
    let active = true
    shell.bootstrap(attempt > 0)
      .then(() => {
        if (active) setState('ready')
      })
      .catch(() => {
        if (active) setState('error')
      })
    return () => { active = false }
  }, [attempt])

  const retry = () => {
    setState('loading')
    setAttempt(value => value + 1)
  }

  if (state === 'loading') {
    return (
      <div className="shell-bootstrap-state" role="status" aria-live="polite">
        <span className="shell-bootstrap-spinner" aria-hidden="true" />
        <p>{t('bootstrap.loading')}</p>
      </div>
    )
  }

  if (state === 'error') {
    return (
      <div className="shell-bootstrap-state" role="alert">
        <h1>{t('bootstrap.unavailable')}</h1>
        <p>{t('bootstrap.unavailableCopy')}</p>
        <button type="button" onClick={retry}>
          {t('common.retry')}
        </button>
      </div>
    )
  }

  return <Outlet />
}
