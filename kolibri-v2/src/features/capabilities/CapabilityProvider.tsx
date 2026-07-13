import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { discoverCapabilities } from './discovery'
import { uiCapabilityMenu } from './uiRegistry'
import type { CapabilityCatalog } from './types'
import { CapabilityContext, type CapabilityContextValue } from './capabilityContext'

const EMPTY_CATALOG: CapabilityCatalog = {
  availability: 'unavailable',
  capabilities: [],
}

export function CapabilityProvider({ children }: { children: ReactNode }) {
  const [catalog, setCatalog] = useState<CapabilityCatalog>(EMPTY_CATALOG)
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      setCatalog(await discoverCapabilities())
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    void discoverCapabilities({ signal: controller.signal })
      .then(setCatalog)
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [])

  useEffect(() => {
    const onFocus = () => { void refresh() }
    window.addEventListener('focus', onFocus)
    return () => window.removeEventListener('focus', onFocus)
  }, [refresh])

  const value = useMemo<CapabilityContextValue>(() => ({
    catalog,
    menu: uiCapabilityMenu(catalog),
    loading,
    refresh,
  }), [catalog, loading, refresh])

  return <CapabilityContext.Provider value={value}>{children}</CapabilityContext.Provider>
}
