import { isUiInvocableCapability } from '@/features/capabilities'
import type { CapabilityCatalog, DiscoveredCapability } from '@/features/capabilities'

export type DeveloperSurface = 'responses' | 'chat' | 'realtime' | 'apiKeys'

const SURFACE_ALIASES: Record<DeveloperSurface, readonly string[]> = {
  responses: ['developer.responses', 'api.responses', 'openai.responses', 'responses.create'],
  chat: ['developer.chat_completions', 'api.chat_completions', 'openai.chat_completions'],
  realtime: ['developer.realtime', 'api.realtime', 'openai.realtime'],
  apiKeys: ['developer.api_keys', 'api_keys.manage'],
}

const SURFACE_RENDERERS: Record<DeveloperSurface, readonly string[]> = {
  responses: ['developer_api', 'responses', 'playground'],
  chat: ['developer_api', 'chat', 'playground'],
  realtime: ['developer_api', 'realtime'],
  apiKeys: ['developer_api_keys', 'api_keys'],
}

function normalized(value: string | undefined): string {
  return value?.trim().toLowerCase() ?? ''
}

export function liveDeveloperCapability(
  catalog: CapabilityCatalog,
  surface: DeveloperSurface,
): DiscoveredCapability | undefined {
  if (catalog.availability === 'unavailable') return undefined
  return catalog.capabilities.find(capability => (
    SURFACE_ALIASES[surface].includes(normalized(capability.id))
    && SURFACE_RENDERERS[surface].includes(normalized(capability.renderer.id))
    && isUiInvocableCapability(capability)
  ))
}

export function isDeveloperSurfaceLive(catalog: CapabilityCatalog, surface: DeveloperSurface): boolean {
  return Boolean(liveDeveloperCapability(catalog, surface))
}

export interface DeveloperEndpoint {
  method: 'GET' | 'POST'
  path: string
  surface: DeveloperSurface
}

const ENDPOINTS: readonly DeveloperEndpoint[] = [
  { method: 'POST', path: '/v1/responses', surface: 'responses' },
  { method: 'POST', path: '/v1/chat/completions', surface: 'chat' },
  { method: 'POST', path: '/v1/realtime/sessions', surface: 'realtime' },
]

export function liveDeveloperEndpoints(catalog: CapabilityCatalog): DeveloperEndpoint[] {
  return ENDPOINTS.filter(endpoint => isDeveloperSurfaceLive(catalog, endpoint.surface))
}
