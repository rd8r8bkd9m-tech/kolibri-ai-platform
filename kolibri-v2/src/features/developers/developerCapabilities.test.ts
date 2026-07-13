import { describe, expect, it } from 'vitest'
import type { CapabilityCatalog, DiscoveredCapability } from '@/features/capabilities'
import { isDeveloperSurfaceLive, liveDeveloperEndpoints } from './developerCapabilities'

function capability(overrides: Partial<DiscoveredCapability> = {}): DiscoveredCapability {
  return {
    id: 'developer.responses',
    name: 'Responses API',
    availability: 'live',
    invocable: true,
    permitted: true,
    route: { healthy: true },
    renderer: { available: true, id: 'developer_api' },
    ...overrides,
  }
}

function catalog(capabilities: DiscoveredCapability[]): CapabilityCatalog {
  return { availability: 'live', capabilities }
}

describe('developer capability gate', () => {
  it('shows only endpoints backed by an exact live capability and renderer', () => {
    const result = liveDeveloperEndpoints(catalog([
      capability(),
      capability({
        id: 'developer.chat_completions',
        name: 'Chat Completions',
        renderer: { available: true, id: 'playground' },
      }),
    ]))

    expect(result.map(endpoint => endpoint.path)).toEqual([
      '/v1/responses',
      '/v1/chat/completions',
    ])
  })

  it('fails closed for incomplete evidence and unrelated capabilities', () => {
    const value = catalog([
      capability({ route: { healthy: false } }),
      capability({ id: 'image.generate', renderer: { available: true, id: 'image' } }),
    ])

    expect(isDeveloperSurfaceLive(value, 'responses')).toBe(false)
    expect(liveDeveloperEndpoints(value)).toEqual([])
  })
})
