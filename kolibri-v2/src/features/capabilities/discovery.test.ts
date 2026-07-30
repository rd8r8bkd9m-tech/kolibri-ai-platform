import { afterEach, describe, expect, it, vi } from 'vitest'

import { discoverCapabilities } from './discovery'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('capability discovery route', () => {
  it('keeps capability reads inside the active immutable canary prefix', async () => {
    vi.stubGlobal('window', { location: { pathname: '/__canary/kolibriai-c41-test/app' } })
    const fetchImpl = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      schema_version: 'kolibri.capabilities.v1',
      status: 'available',
      as_of: '2026-07-16T00:00:00Z',
      counts: { available: 0, degraded: 0, unavailable: 0 },
      capabilities: [],
    }), { status: 200, headers: { 'content-type': 'application/json' } }))

    await discoverCapabilities({ fetchImpl })

    expect(fetchImpl).toHaveBeenCalledWith(
      '/__canary/kolibriai-c41-test/api/v1/capabilities',
      expect.objectContaining({ method: 'GET' }),
    )
  })

  it('uses the public API root outside a canary', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(new Response('{}', {
      status: 500,
      headers: { 'content-type': 'application/json' },
    }))

    await discoverCapabilities({ fetchImpl })

    expect(fetchImpl).toHaveBeenCalledWith(
      '/api/v1/capabilities',
      expect.objectContaining({ method: 'GET' }),
    )
  })
})
