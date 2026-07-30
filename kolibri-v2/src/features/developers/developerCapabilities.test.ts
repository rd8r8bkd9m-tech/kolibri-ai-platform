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
      '/v1/models',
      '/v1/responses',
      '/v1/chat/completions',
    ])
  })

  it('uses the exact live Responses manifest IDs emitted by the backend', () => {
    const result = liveDeveloperEndpoints(catalog([
      capability({
        id: 'openai.web_search',
        name: 'Web search',
        route: {},
        renderer: {},
        permitted: undefined,
        sourceType: 'live_invocation',
      }),
    ]))

    expect(result.map(endpoint => endpoint.path)).toEqual([
      '/v1/models',
      '/v1/responses',
      '/v1/chat/completions',
    ])
  })

  it('publishes the compatible API when the backend proves chat.responses by live invocation', () => {
    const result = liveDeveloperEndpoints(catalog([
      capability({
        id: 'chat.responses',
        name: 'Chat responses',
        route: {},
        renderer: {},
        permitted: undefined,
        sourceType: 'live_invocation',
      }),
    ]))

    expect(result.map(endpoint => endpoint.path)).toEqual([
      '/v1/models',
      '/v1/responses',
      '/v1/chat/completions',
    ])
  })

  it('does not infer a developer route from configured-only provider tools', () => {
    const value = catalog([
      capability({
        id: 'openai.web_search',
        name: 'Web search',
        availability: 'partial',
        invocable: false,
        route: {},
        renderer: {},
        permitted: undefined,
        sourceType: 'configuration',
      }),
    ])

    expect(liveDeveloperEndpoints(value)).toEqual([])
  })

  it('fails closed for incomplete evidence and unrelated capabilities', () => {
    const value = catalog([
      capability({ route: { healthy: false } }),
      capability({ id: 'image.generate', renderer: { available: true, id: 'image' } }),
    ])

    expect(isDeveloperSurfaceLive(value, 'responses')).toBe(false)
    expect(liveDeveloperEndpoints(value)).toEqual([])
  })

  it('opens key management only for the live API-key renderer contract', () => {
    const value = catalog([
      capability({
        id: 'developer.api_keys',
        renderer: { available: true, id: 'developer_api_keys' },
      }),
    ])

    expect(isDeveloperSurfaceLive(value, 'apiKeys')).toBe(true)
    expect(isDeveloperSurfaceLive(catalog([
      capability({
        id: 'developer.api_keys',
        renderer: { available: true, id: 'developer_api' },
      }),
    ]), 'apiKeys')).toBe(false)
  })
})
