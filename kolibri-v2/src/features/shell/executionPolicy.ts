import type { ChatExecutionMode, ChatExecutionPolicy } from '@/lib/api'

export const EXECUTION_MODE_STORAGE_KEY = 'kolibri_execution_mode'

export function createExecutionPolicy(
  mode: ChatExecutionMode,
  allowedCapabilities: readonly string[],
  explicitlyRequestedCapabilities: readonly string[] = [],
): ChatExecutionPolicy {
  // The visible menu contains only capabilities with a completed probe. A
  // natural-language request is also an explicit invocation signal and must
  // be able to perform the first real probe of a configured route. The
  // backend remains the policy and credential authority.
  const requestedCapabilities = [...new Set([
    ...allowedCapabilities,
    ...explicitlyRequestedCapabilities,
  ])].sort()
  return {
    mode,
    reasoning_effort: mode === 'deep' ? 'high' : 'low',
    tool_choice: 'auto',
    background: mode === 'deep',
    allowed_capabilities: requestedCapabilities,
  }
}
