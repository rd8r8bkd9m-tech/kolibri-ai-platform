import { createContext, useContext } from 'react'
import type { CapabilityCatalog, UiCapability } from './types'

export interface CapabilityContextValue {
  catalog: CapabilityCatalog
  menu: UiCapability[]
  loading: boolean
  refresh: () => Promise<void>
}

export const CapabilityContext = createContext<CapabilityContextValue | null>(null)

export function useCapabilities(): CapabilityContextValue {
  const value = useContext(CapabilityContext)
  if (!value) throw new Error('useCapabilities must be used inside CapabilityProvider')
  return value
}
