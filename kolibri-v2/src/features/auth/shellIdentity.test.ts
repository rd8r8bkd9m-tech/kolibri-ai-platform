import { describe, expect, it } from 'vitest'
import type { AuthUser } from '@/lib/api'
import { verifiedDisplayName, verifiedFirstName, verifiedInitials } from './shellIdentity'

const user: AuthUser = {
  id: 'user-1',
  email: 'user@example.test',
  name: '  Анна   Петрова  ',
  role: 'user',
}

describe('verified Shell identity', () => {
  it('never invents an owner identity for a guest session', () => {
    expect(verifiedDisplayName(null)).toBeNull()
    expect(verifiedFirstName(null)).toBeNull()
    expect(verifiedInitials(null)).toBeNull()
  })

  it('normalizes the display name returned by the authenticated session', () => {
    expect(verifiedDisplayName(user)).toBe('Анна Петрова')
    expect(verifiedFirstName(user)).toBe('Анна')
    expect(verifiedInitials(user)).toBe('АП')
  })

  it('treats an empty authenticated name as non-personalized', () => {
    expect(verifiedDisplayName({ ...user, name: '   ' })).toBeNull()
    expect(verifiedFirstName({ ...user, name: '   ' })).toBeNull()
    expect(verifiedInitials({ ...user, name: '   ' })).toBeNull()
  })
})
