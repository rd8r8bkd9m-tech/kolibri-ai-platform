export type CapabilityAvailability = 'live' | 'partial' | 'unavailable'

export interface CapabilityRouteEvidence {
  id?: string
  healthy?: boolean
  status?: string
  provider?: string
  model?: string
  configured?: boolean
  permitted?: boolean
  credentialReady?: boolean
  probeState?: string
  probeFresh?: boolean
}

export interface CapabilityRendererEvidence {
  available?: boolean
  id?: string
  status?: string
  required?: boolean
  registered?: boolean
  healthy?: boolean
}

export type UiCapabilityKey =
  | 'document.editor'
  | 'web.search'
  | 'file.search'
  | 'document.pdf'
  | 'document.docx'
  | 'document.xlsx'
  | 'document.pptx'
  | 'code.execute'
  | 'image.generate'
  | 'image.edit'
  | 'site.create'
  | 'app.create'
  | 'browser.use'
  | 'mcp.invoke'

export interface UiCapability {
  key: UiCapabilityKey
  capability: DiscoveredCapability
  title: string
  description: string
  enabled: boolean
  disabledReason?: string
}

export interface DiscoveredCapability {
  id: string
  name: string
  description?: string
  kind?: string
  availability: CapabilityAvailability
  availabilityReason?: string
  reasonCode?: string
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
