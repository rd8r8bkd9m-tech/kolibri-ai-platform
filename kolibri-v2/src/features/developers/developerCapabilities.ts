import { isUiInvocableCapability } from '@/features/capabilities'
import type { CapabilityCatalog, DiscoveredCapability } from '@/features/capabilities'

export type DeveloperSurface = 'responses' | 'chat' | 'realtime' | 'apiKeys'

// The public backend advertises the Responses provider through the exact
// capability IDs below. A live item is backed by a successful tool invocation,
// so it is stronger evidence than a configured-only provider flag.
const RESPONSES_MANIFEST_IDS = [
  'openai.web_search',
  'openai.file_search',
  'openai.code_interpreter',
  'openai.image_generation',
  'openai.remote_mcp',
  'openai.computer',
  'openai.multi_agent',
] as const

const SURFACE_ALIASES: Record<DeveloperSurface, readonly string[]> = {
  responses: ['developer.responses', 'api.responses', 'openai.responses', 'responses.create', 'chat.responses', ...RESPONSES_MANIFEST_IDS],
  chat: ['developer.chat_completions', 'api.chat_completions', 'openai.chat_completions', 'chat.responses', ...RESPONSES_MANIFEST_IDS],
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

function isLiveResponsesManifestProbe(capability: DiscoveredCapability, surface: DeveloperSurface): boolean {
  if (surface !== 'responses' && surface !== 'chat') return false
  const id = normalized(capability.id)
  return (RESPONSES_MANIFEST_IDS.includes(id as typeof RESPONSES_MANIFEST_IDS[number]) || id === 'chat.responses')
    && capability.availability === 'live'
    && capability.invocable
    && capability.sourceType === 'live_invocation'
}

export function liveDeveloperCapability(
  catalog: CapabilityCatalog,
  surface: DeveloperSurface,
): DiscoveredCapability | undefined {
  if (catalog.availability === 'unavailable') return undefined
  return catalog.capabilities.find(capability => (
    SURFACE_ALIASES[surface].includes(normalized(capability.id))
    && (
      isLiveResponsesManifestProbe(capability, surface)
      || (
        SURFACE_RENDERERS[surface].includes(normalized(capability.renderer.id))
        && isUiInvocableCapability(capability)
      )
    )
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
  { method: 'GET', path: '/v1/models', surface: 'responses' },
  { method: 'POST', path: '/v1/responses', surface: 'responses' },
  { method: 'POST', path: '/v1/chat/completions', surface: 'chat' },
  { method: 'POST', path: '/v1/realtime/sessions', surface: 'realtime' },
]

export function liveDeveloperEndpoints(catalog: CapabilityCatalog): DeveloperEndpoint[] {
  return ENDPOINTS.filter(endpoint => isDeveloperSurfaceLive(catalog, endpoint.surface))
}
