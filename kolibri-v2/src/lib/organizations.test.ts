import { afterEach, describe, expect, it, vi } from 'vitest'
import { organizations } from './api'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('organization API contracts', () => {
  it('uses same-origin cookie requests and never sends a client organization selector', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ items: [] }))
    vi.stubGlobal('fetch', fetchMock)

    await organizations.list()

    expect(fetchMock).toHaveBeenCalledWith('/api/v1/organizations', expect.objectContaining({
      cache: 'no-store',
      credentials: 'include',
    }))
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit
    expect(new Headers(init.headers).has('X-Kolibri-Organization')).toBe(false)
    expect(new Headers(init.headers).has('Authorization')).toBe(false)
  })

  it('matches select, membership, role and suspension routes exactly', async () => {
    const membership = {
      id: 'member/id',
      organization_id: 'org/id',
      user: { id: 'user_1', email: 'user@example.ru', name: 'Пользователь' },
      role: 'member',
      status: 'active',
      created_at: '2026-07-16T10:00:00Z',
      updated_at: '2026-07-16T10:00:00Z',
    }
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ selected: true }))
      .mockResolvedValueOnce(jsonResponse({ items: [membership] }))
      .mockResolvedValueOnce(jsonResponse(membership, 201))
      .mockResolvedValueOnce(jsonResponse({ ...membership, role: 'admin' }))
      .mockResolvedValueOnce(jsonResponse({ ...membership, status: 'suspended' }))
    vi.stubGlobal('fetch', fetchMock)

    await organizations.select('org/id')
    await organizations.memberships('org/id')
    await organizations.invite('org/id', { email: 'user@example.ru', role: 'member' })
    await organizations.changeRole('org/id', 'member/id', 'admin')
    await organizations.suspend('org/id', 'member/id')

    expect(fetchMock.mock.calls.map(call => call[0])).toEqual([
      '/api/v1/organizations/org%2Fid/select',
      '/api/v1/organizations/org%2Fid/memberships',
      '/api/v1/organizations/org%2Fid/memberships',
      '/api/v1/organizations/org%2Fid/memberships/member%2Fid',
      '/api/v1/organizations/org%2Fid/memberships/member%2Fid/suspend',
    ])
    expect(fetchMock.mock.calls.map(call => (call[1] as RequestInit).method ?? 'GET')).toEqual([
      'POST', 'GET', 'POST', 'PATCH', 'POST',
    ])
    expect((fetchMock.mock.calls[2]?.[1] as RequestInit).body).toBe(JSON.stringify({
      email: 'user@example.ru',
      role: 'member',
    }))
    expect((fetchMock.mock.calls[3]?.[1] as RequestInit).body).toBe(JSON.stringify({ role: 'admin' }))
    expect(fetchMock.mock.calls.every(call => (call[1] as RequestInit).credentials === 'include')).toBe(true)
    expect(fetchMock.mock.calls.every(call => !new Headers((call[1] as RequestInit).headers).has('X-Kolibri-Organization'))).toBe(true)
  })
})
