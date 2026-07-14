import { describe, expect, it } from 'vitest'
import { ownerRouteTarget } from './ownerAccess'
import type { AuthUser } from '@/lib/api'

function user(role: string): AuthUser {
  return { id: role, email: `${role}@example.test`, name: role, role }
}

describe('owner route authorization UX', () => {
  it('redirects guests to login and authenticated non-owners home', () => {
    expect(ownerRouteTarget(null)).toBe('/login')
    expect(ownerRouteTarget(user('user'))).toBe('/')
  })

  it.each(['owner', 'admin', 'superadmin', ' OWNER '])('allows operator role %s', role => {
    expect(ownerRouteTarget(user(role))).toBeNull()
  })
})
