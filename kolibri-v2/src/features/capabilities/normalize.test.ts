import { describe, expect, it } from 'vitest'
import { isUiInvocableCapability, normalizeCapabilityCatalog } from './normalize'
import { uiCapabilityMenu } from './uiRegistry'
import type { DiscoveredCapability } from './types'

function capability(overrides: Partial<DiscoveredCapability> = {}): DiscoveredCapability {
  return {
    id: 'image.generate',
    name: 'Изображение',
    availability: 'live',
    invocable: true,
    permitted: true,
    route: { healthy: true, status: 'live' },
    renderer: { available: true, id: 'image', status: 'live' },
    ...overrides,
  }
}

describe('capability UI gate', () => {
  it('requires explicit route, renderer and policy evidence', () => {
    expect(isUiInvocableCapability(capability())).toBe(true)
    expect(isUiInvocableCapability(capability({ route: {} }))).toBe(false)
    expect(isUiInvocableCapability(capability({ renderer: { available: true } }))).toBe(false)
    expect(isUiInvocableCapability(capability({ permitted: undefined }))).toBe(false)
  })

  it('shows only capabilities with a renderer supported by this Shell', () => {
    const catalog = {
      availability: 'live' as const,
      capabilities: [
        capability(),
        capability({ id: 'web.search', name: 'Интернет', renderer: { available: true, id: 'sources' } }),
        capability({ id: 'code.execute', name: 'Код', renderer: { available: true, id: 'unsupported' } }),
      ],
    }
    expect(uiCapabilityMenu(catalog).map(item => item.key)).toEqual(['web.search', 'image.generate'])
  })

  it('normalizes an explicit live backend contract without optimistic defaults', () => {
    const catalog = normalizeCapabilityCatalog({
      status: 'live',
      capabilities: [{
        id: 'browser.use',
        name: 'Браузер',
        status: 'live',
        invocable: true,
        permitted: true,
        route: { healthy: true, status: 'live' },
        renderer: { available: true, id: 'browser', status: 'live' },
      }],
    })
    expect(uiCapabilityMenu(catalog).map(item => item.key)).toEqual(['browser.use'])
  })
})
