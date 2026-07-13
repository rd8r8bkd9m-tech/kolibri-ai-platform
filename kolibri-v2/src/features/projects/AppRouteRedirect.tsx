import { useEffect, useMemo, useState } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router'
import { useLocale } from '@/features/localization'
import { projects } from '@/lib/api'
import { appRouteTarget } from './appRoute'
import {
  handoffClaimStatus,
  handoffRequestKey,
  handoffRouteKey,
  isTerminalHandoffClaimError,
  shouldStripHandoffFragment,
  type HandoffClaimResult,
} from './appRouteHandoff'

function stripHandoffFragment() {
  try {
    window.history.replaceState(window.history.state, '', `${window.location.pathname}${window.location.search}`)
  } catch {
    // Successful navigation removes the fragment as a fallback. Sandboxed
    // clients may reject direct History API writes on the terminal screen.
  }
}

export default function AppRouteRedirect() {
  const { t } = useLocale()
  const { search, hash } = useLocation()
  const navigate = useNavigate()
  const projectId = useMemo(() => new URLSearchParams(search).get('project')?.trim() ?? '', [search])
  const handoff = useMemo(() => new URLSearchParams(hash.slice(1)).get('handoff')?.trim() ?? '', [hash])
  const routeKey = useMemo(() => handoffRouteKey(projectId, handoff), [handoff, projectId])
  const [attempt, setAttempt] = useState(0)
  const requestKey = useMemo(() => handoffRequestKey(routeKey, attempt), [attempt, routeKey])
  const [result, setResult] = useState<HandoffClaimResult | null>(null)
  const state = handoffClaimStatus(routeKey, requestKey, result)

  useEffect(() => {
    if (!routeKey) return
    let active = true
    projects.claim(projectId, handoff)
      .then(() => {
        if (!active) return
        const status = 'ready'
        if (shouldStripHandoffFragment(status)) stripHandoffFragment()
        setResult({ requestKey, status })
      })
      .catch(error => {
        if (!active) return
        const status = isTerminalHandoffClaimError(error) ? 'failed' : 'retryable'
        if (shouldStripHandoffFragment(status)) stripHandoffFragment()
        setResult({ requestKey, status })
      })
    return () => { active = false }
  }, [handoff, projectId, requestKey, routeKey])

  if (state === 'claiming') {
    return <div role="status" className="flex h-[100dvh] items-center justify-center px-6 text-center text-[var(--text-secondary)]">{t('handoff.opening')}</div>
  }
  if (state === 'failed') {
    return (
      <div role="alert" className="flex h-[100dvh] flex-col items-center justify-center gap-4 px-6 text-center text-[var(--text-secondary)]">
        <p>{t('handoff.invalid')}</p>
        <button type="button" className="font-medium text-[var(--accent-teal)]" onClick={() => navigate('/chat', { replace: true })}>{t('handoff.newChat')}</button>
      </div>
    )
  }
  if (state === 'retryable') {
    return (
      <div role="alert" className="flex h-[100dvh] flex-col items-center justify-center gap-4 px-6 text-center text-[var(--text-secondary)]">
        <p>{t('handoff.temporary')}</p>
        <div className="flex flex-wrap items-center justify-center gap-4">
          <button type="button" className="font-medium text-[var(--accent-teal)]" onClick={() => setAttempt(value => value + 1)}>{t('handoff.retry')}</button>
          <button type="button" className="font-medium text-[var(--text-tertiary)]" onClick={() => navigate('/chat', { replace: true })}>{t('handoff.newChat')}</button>
        </div>
      </div>
    )
  }
  return <Navigate to={appRouteTarget(search)} replace />
}
