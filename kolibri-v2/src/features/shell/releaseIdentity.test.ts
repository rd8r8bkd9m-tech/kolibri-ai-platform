import { describe, expect, it } from 'vitest'
import { isOwnerRole, safeBuildReleaseId } from './releaseIdentity'

describe('owner build diagnostics release identity', () => {
  it('accepts the signed release naming contract and rejects unsafe values', () => {
    expect(safeBuildReleaseId('kolibri-r17-test')).toBe('kolibri-r17-test')
    expect(safeBuildReleaseId('<script>alert(1)</script>')).toBeNull()
    expect(safeBuildReleaseId('')).toBeNull()
  })

  it('limits diagnostics to owner roles', () => {
    expect(isOwnerRole('owner')).toBe(true)
    expect(isOwnerRole('ADMIN')).toBe(true)
    expect(isOwnerRole('user')).toBe(false)
    expect(isOwnerRole(undefined)).toBe(false)
  })
})
