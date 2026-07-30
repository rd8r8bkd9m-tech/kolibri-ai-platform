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

  it('does not invent legacy estimate or document tools when discovery is empty', () => {
    expect(uiCapabilityMenu({ availability: 'unavailable', capabilities: [] })).toEqual([])
  })

  it('hides canonical degraded capabilities until a fresh invocation makes them invocable', () => {
    const catalog = normalizeCapabilityCatalog({
      status: 'degraded',
      capabilities: [{
        id: 'document.pdf',
        name: 'PDF',
        status: 'degraded',
        invocable: false,
        policy: { permitted: true },
        renderer: { required: true, id: 'pdf', registered: true, healthy: null },
        routes: [{
          id: 'kolibri-backend',
          configured: true,
          permitted: true,
          credential: { ready: true },
          probe: { state: 'never', fresh: false },
        }],
      }],
    })
    expect(uiCapabilityMenu(catalog)).toEqual([])
  })

  it('shows estimate and document editors only from their exact live backend contracts', () => {
    const catalog = {
      availability: 'partial' as const,
      capabilities: [
        capability({ id: 'estimate.create', name: 'Смета', renderer: { available: true, id: 'estimate_editor' } }),
        capability({ id: 'document.editor', name: 'Документ', renderer: { available: true, id: 'document_editor' } }),
        capability({ id: 'estimate.create', name: 'Непроверенная смета', route: { healthy: false }, renderer: { available: true, id: 'estimate_editor' } }),
      ],
    }
    expect(uiCapabilityMenu(catalog).map(item => item.key)).toEqual(['estimate.create', 'document.editor'])
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

  it('keeps a topology-free public capability invocable', () => {
    const payload = {
      status: 'available',
      capabilities: [{
        id: 'image.generate',
        name: 'Изображение',
        status: 'available',
        invocable: true,
        permitted: true,
        route: { healthy: true, status: 'available' },
        renderer: {
          required: true,
          id: 'image',
          registered: true,
          healthy: true,
        },
        reason: {
          code: 'live_invocation',
          message: 'Маршрут подтверждён.',
        },
      }],
    }

    const catalog = normalizeCapabilityCatalog(payload)
    expect(isUiInvocableCapability(catalog.capabilities[0])).toBe(true)
    expect(uiCapabilityMenu(catalog).map(item => item.key)).toContain('image.generate')
    expect(JSON.stringify(payload)).not.toMatch(/codex|mimo|deepseek|provider|credential|selected_route/i)
  })
})
