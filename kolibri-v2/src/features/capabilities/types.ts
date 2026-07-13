export type CapabilityAvailability = 'live' | 'partial' | 'unavailable'

export interface CapabilityRouteEvidence {
  healthy?: boolean
  status?: string
  provider?: string
  model?: string
}

export interface CapabilityRendererEvidence {
  available?: boolean
  id?: string
  status?: string
}

export type UiCapabilityKey =
  | 'web.search'
  | 'file.search'
  | 'code.execute'
  | 'image.generate'
  | 'browser.use'
  | 'mcp.invoke'

export interface UiCapability {
  key: UiCapabilityKey
  capability: DiscoveredCapability
  title: string
  description: string
}

export interface DiscoveredCapability {
  id: string
  name: string
  description?: string
  kind?: string
  availability: CapabilityAvailability
  availabilityReason?: string
  invocable: boolean
  permitted?: boolean
  route: CapabilityRouteEvidence
  renderer: CapabilityRendererEvidence
  sourceType?: string
}

export interface CapabilityCatalogIssue {
  code: 'invalid_payload' | 'http_error' | 'network_error'
  message: string
  status?: number
}

export interface CapabilityCatalog {
  schemaVersion?: string
  availability: CapabilityAvailability
  capabilities: DiscoveredCapability[]
  asOf?: string
  issue?: CapabilityCatalogIssue
}

export interface CapabilityDiscoveryOptions {
  endpoint?: string
  fetchImpl?: typeof fetch
  signal?: AbortSignal
}
