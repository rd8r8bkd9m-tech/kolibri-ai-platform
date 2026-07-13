import { describe, expect, it } from 'vitest'
import { ApiError } from '@/lib/api'
import {
  handoffClaimStatus,
  handoffRequestKey,
  handoffRouteKey,
  isTerminalHandoffClaimError,
  shouldStripHandoffFragment,
  type HandoffClaimResult,
} from './appRouteHandoff'

describe('Telegram project handoff state', () => {
  it('distinguishes terminal bearer failures from retryable transport and server failures', () => {
    for (const status of [400, 404, 410, 422]) {
      expect(isTerminalHandoffClaimError(new ApiError(status, 'terminal'))).toBe(true)
    }
    expect(isTerminalHandoffClaimError(new ApiError(429, 'retry later'))).toBe(false)
    expect(isTerminalHandoffClaimError(new ApiError(503, 'unavailable'))).toBe(false)
    expect(isTerminalHandoffClaimError(new TypeError('offline'))).toBe(false)
    expect(shouldStripHandoffFragment('failed')).toBe(true)
    expect(shouldStripHandoffFragment('retryable')).toBe(false)
  })

  it('shows a fresh claim when the route or retry attempt changes', () => {
    const firstRoute = handoffRouteKey('project_1', 'A'.repeat(43))
    const firstRequest = handoffRequestKey(firstRoute, 0)
    const failed: HandoffClaimResult = { requestKey: firstRequest, status: 'failed' }

    expect(handoffClaimStatus(firstRoute, firstRequest, failed)).toBe('failed')

    const secondRoute = handoffRouteKey('project_2', 'B'.repeat(43))
    const secondRequest = handoffRequestKey(secondRoute, 0)
    expect(handoffClaimStatus(secondRoute, secondRequest, failed)).toBe('claiming')
    expect(handoffClaimStatus(firstRoute, handoffRequestKey(firstRoute, 1), failed)).toBe('claiming')
  })

  it('returns to compatibility redirect state when a reused /app route has no handoff', () => {
    const previousRoute = handoffRouteKey('project_1', 'A'.repeat(43))
    const previousRequest = handoffRequestKey(previousRoute, 0)
    const previous: HandoffClaimResult = { requestKey: previousRequest, status: 'retryable' }

    expect(handoffClaimStatus('', handoffRequestKey('', 0), previous)).toBe('ready')
  })
})
