import { ApiError } from '@/lib/api'

export type HandoffClaimStatus = 'claiming' | 'ready' | 'retryable' | 'failed'
export type SettledHandoffClaimStatus = Exclude<HandoffClaimStatus, 'claiming'>

export interface HandoffClaimResult {
  requestKey: string
  status: SettledHandoffClaimStatus
}

const TERMINAL_CLAIM_STATUSES = new Set([400, 404, 410, 422])

export function isTerminalHandoffClaimError(error: unknown): boolean {
  return error instanceof ApiError && TERMINAL_CLAIM_STATUSES.has(error.status)
}

export function shouldStripHandoffFragment(status: SettledHandoffClaimStatus): boolean {
  return status !== 'retryable'
}

export function handoffRouteKey(projectId: string, handoff: string): string {
  return projectId && handoff ? JSON.stringify([projectId, handoff]) : ''
}

export function handoffRequestKey(routeKey: string, attempt: number): string {
  return JSON.stringify([routeKey, attempt])
}

export function handoffClaimStatus(
  routeKey: string,
  requestKey: string,
  result: HandoffClaimResult | null,
): HandoffClaimStatus {
  if (!routeKey) return 'ready'
  return result?.requestKey === requestKey ? result.status : 'claiming'
}
