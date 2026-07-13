import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  developerApiKeys,
  getDeveloperOwnerToken,
  setDeveloperOwnerToken,
} from './api'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

const key = {
  id: 'key_contract',
  object: 'api_key' as const,
  name: 'CLI',
  prefix: 'koli_live_abcd',
  created_at: 1_784_000_000,
  last_used_at: null,
  revoked: false,
  revoked_at: null,
}

afterEach(() => {
  setDeveloperOwnerToken(null)
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('developer API key owner contract', () => {
  it('keeps the owner token in the tab session and never localStorage', () => {
    const session = {
      getItem: vi.fn(),
      setItem: vi.fn(),
      removeItem: vi.fn(),
    }
    const local = {
      getItem: vi.fn(),
      setItem: vi.fn(),
      removeItem: vi.fn(),
    }
    vi.stubGlobal('sessionStorage', session)
    vi.stubGlobal('localStorage', local)

    setDeveloperOwnerToken('owner-session-token')

    expect(getDeveloperOwnerToken()).toBe('owner-session-token')
    expect(session.setItem).toHaveBeenCalledWith(
      'kolibri_developer_owner_token',
      'owner-session-token',
    )
    expect(local.setItem).not.toHaveBeenCalled()
  })

  it('uses the exact owner routes, header, and data/secret response fields', async () => {
    const created = { ...key, secret: 'koli_live_one_time_secret', secret_shown_once: true as const }
    const revoked = { ...key, revoked: true, revoked_at: 1_784_000_100 }
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(created, 201))
      .mockResolvedValueOnce(jsonResponse({ object: 'list', data: [key] }))
      .mockResolvedValueOnce(jsonResponse(revoked))
    vi.stubGlobal('fetch', fetchMock)

    await expect(developerApiKeys.create('CLI', 'owner-token')).resolves.toEqual(created)
    await expect(developerApiKeys.list('owner-token')).resolves.toEqual({ object: 'list', data: [key] })
    await expect(developerApiKeys.revoke('key/contract', 'owner-token')).resolves.toEqual(revoked)

    expect(fetchMock.mock.calls.map(call => call[0])).toEqual([
      '/api/v1/developer/api-keys',
      '/api/v1/developer/api-keys',
      '/api/v1/developer/api-keys/key%2Fcontract',
    ])
    expect(fetchMock.mock.calls.map(call => (call[1] as RequestInit).method)).toEqual([
      'POST',
      undefined,
      'DELETE',
    ])
    for (const [, init] of fetchMock.mock.calls) {
      expect(init).toEqual(expect.objectContaining({
        cache: 'no-store',
        credentials: 'include',
        headers: expect.objectContaining({
          'X-Kolibri-Owner-Token': 'owner-token',
        }),
      }))
      expect((init as RequestInit).headers).not.toHaveProperty('Idempotency-Key')
    }
  })
})
