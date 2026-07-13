import type { ChatExecutionMode, ChatExecutionPolicy } from '@/lib/api'

export const EXECUTION_MODE_STORAGE_KEY = 'kolibri_execution_mode'

export function createExecutionPolicy(
  mode: ChatExecutionMode,
  allowedCapabilities: readonly string[],
): ChatExecutionPolicy {
  return {
    mode,
    reasoning_effort: mode === 'deep' ? 'high' : 'low',
    tool_choice: 'auto',
    background: mode === 'deep',
    allowed_capabilities: [...allowedCapabilities],
  }
}
