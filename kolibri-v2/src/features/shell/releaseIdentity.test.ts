import { describe, expect, it } from 'vitest'
import { isOwnerRole, publishBuildReleaseIdentity, safeBuildReleaseId } from './releaseIdentity'

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

  it('publishes the real sanitized build release id for browser evidence', () => {
    const attributes = new Map<string, string>()
    const target = {
      document: {
        documentElement: {
          setAttribute: (name: string, value: string) => attributes.set(name, value),
        },
      },
    } as unknown as typeof globalThis & { KOLIBRI_RELEASE_ID?: string; document: Document }

    expect(publishBuildReleaseIdentity(target, 'kolibri-p7-20260715-9336cd8-c6')).toBe('kolibri-p7-20260715-9336cd8-c6')
    expect(target.KOLIBRI_RELEASE_ID).toBe('kolibri-p7-20260715-9336cd8-c6')
    expect(attributes.get('data-kolibri-release-id')).toBe('kolibri-p7-20260715-9336cd8-c6')
  })

  it('does not publish unsafe or missing build release ids', () => {
    const target = {} as typeof globalThis & { KOLIBRI_RELEASE_ID?: string }

    expect(publishBuildReleaseIdentity(target, '<stale-script>')).toBeNull()
    expect(target.KOLIBRI_RELEASE_ID).toBeUndefined()
  })
})
