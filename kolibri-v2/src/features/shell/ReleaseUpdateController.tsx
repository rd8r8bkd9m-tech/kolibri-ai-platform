import { useCallback, useEffect, useRef, useState } from 'react'
import { RefreshCw } from 'lucide-react'
import { activeModuleAsset, frontendUpdateAvailable } from './releaseUpdate'
import { RESPONSE_ACTIVITY_EVENT, updateActiveResponseIds, type ResponseActivityDetail } from './responseActivity'
import { useLocale } from '@/features/localization'

const CHECK_INTERVAL_MS = 60_000

export default function ReleaseUpdateController() {
  const { t } = useLocale()
  const [available, setAvailable] = useState(false)
  const [responseActive, setResponseActive] = useState(false)
  const [reloadRequested, setReloadRequested] = useState(false)
  const checking = useRef(false)
  const activeResponseIds = useRef<Set<string>>(new Set())

  const check = useCallback(async () => {
    if (checking.current || available) return
    const currentAsset = activeModuleAsset()
    if (!currentAsset) return
    checking.current = true
    try {
      if (await frontendUpdateAvailable(currentAsset)) setAvailable(true)
    } catch {
      // A failed probe never interrupts the current product session.
    } finally {
      checking.current = false
    }
  }, [available])

  useEffect(() => {
    const initial = window.setTimeout(() => void check(), 0)
    const interval = window.setInterval(() => void check(), CHECK_INTERVAL_MS)
    const onVisible = () => { if (document.visibilityState === 'visible') void check() }
    const onFocus = () => void check()
    const onOnline = () => void check()
    document.addEventListener('visibilitychange', onVisible)
    window.addEventListener('focus', onFocus)
    window.addEventListener('online', onOnline)
    return () => {
      window.clearTimeout(initial)
      window.clearInterval(interval)
      document.removeEventListener('visibilitychange', onVisible)
      window.removeEventListener('focus', onFocus)
      window.removeEventListener('online', onOnline)
    }
  }, [check])

  useEffect(() => {
    const onResponseState = (event: Event) => {
      const detail = (event as CustomEvent<Partial<ResponseActivityDetail>>).detail
      activeResponseIds.current = updateActiveResponseIds(activeResponseIds.current, detail)
      setResponseActive(activeResponseIds.current.size > 0)
    }
    window.addEventListener(RESPONSE_ACTIVITY_EVENT, onResponseState)
    return () => window.removeEventListener(RESPONSE_ACTIVITY_EVENT, onResponseState)
  }, [])

  useEffect(() => {
    if (reloadRequested && !responseActive) window.location.reload()
  }, [reloadRequested, responseActive])

  if (!available) return null

  const requestReload = () => {
    if (responseActive) setReloadRequested(true)
    else window.location.reload()
  }

  return (
    <div role="status" aria-live="polite" className="fixed inset-x-3 top-[max(12px,env(safe-area-inset-top))] z-[120] mx-auto flex min-h-12 max-w-md items-center gap-3 rounded-2xl border border-black/10 bg-white/95 px-4 py-2.5 text-[14px] text-black shadow-lg backdrop-blur-xl dark:border-white/10 dark:bg-[#202020]/95 dark:text-white">
      <RefreshCw size={18} aria-hidden="true" className="shrink-0" />
      <span className="min-w-0 flex-1">{reloadRequested ? t('release.waiting') : t('release.available')}</span>
      <button type="button" onClick={requestReload} disabled={reloadRequested} className="min-h-11 shrink-0 rounded-xl px-2 font-semibold text-[var(--accent-teal)] disabled:opacity-60">
        {responseActive ? t('release.afterResponse') : t('release.reload')}
      </button>
    </div>
  )
}
