import { useMemo, useState, type ReactNode } from 'react'
import type { ChatExecutionMode } from '@/lib/api'
import { EXECUTION_MODE_STORAGE_KEY } from './executionPolicy'
import { ExecutionPolicyContext, type ExecutionPolicyContextValue } from './executionPolicyContext'

function initialMode(): ChatExecutionMode {
  return localStorage.getItem(EXECUTION_MODE_STORAGE_KEY) === 'fast' ? 'fast' : 'deep'
}

export function ExecutionPolicyProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<ChatExecutionMode>(initialMode)
  const value = useMemo<ExecutionPolicyContextValue>(() => ({
    mode,
    setMode: next => {
      localStorage.setItem(EXECUTION_MODE_STORAGE_KEY, next)
      setModeState(next)
    },
  }), [mode])

  return <ExecutionPolicyContext.Provider value={value}>{children}</ExecutionPolicyContext.Provider>
}
