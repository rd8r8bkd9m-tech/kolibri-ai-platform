import { createContext, useContext } from 'react'
import type { ChatExecutionMode } from '@/lib/api'

export interface ExecutionPolicyContextValue {
  mode: ChatExecutionMode
  setMode: (mode: ChatExecutionMode) => void
}

export const ExecutionPolicyContext = createContext<ExecutionPolicyContextValue | null>(null)

export function useExecutionMode(): ExecutionPolicyContextValue {
  const value = useContext(ExecutionPolicyContext)
  if (!value) throw new Error('useExecutionMode must be used inside ExecutionPolicyProvider')
  return value
}
