import type {
  CapabilityAvailability,
  CapabilityCatalog,
  CapabilityRendererEvidence,
  CapabilityRouteEvidence,
  DiscoveredCapability,
} from './types'

type UnknownRecord = Record<string, unknown>

const LIVE_STATES = new Set([
  'active',
  'available',
  'enabled',
  'healthy',
  'live',
  'ok',
  'online',
  'ready',
  'working',
])

const PARTIAL_STATES = new Set([
  'degraded',
  'limited',
  'partial',
  'stale',
  'warning',
])

const UNAVAILABLE_STATES = new Set([
  'blocked',
  'disabled',
  'error',
  'failed',
  'inactive',
  'offline',
  'unavailable',
  'unhealthy',
  'unknown',
])

function isRecord(value: unknown): value is UnknownRecord {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function stringValue(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() ? value.trim() : undefined
}

function booleanValue(value: unknown): boolean | undefined {
  if (typeof value === 'boolean') return value
  if (value === 'true') return true
  if (value === 'false') return false
  return undefined
}

function nestedRecord(record: UnknownRecord, key: string): UnknownRecord | undefined {
  const value = record[key]
  return isRecord(value) ? value : undefined
}

function firstBoolean(...values: unknown[]): boolean | undefined {
  for (const value of values) {
    const normalized = booleanValue(value)
    if (normalized !== undefined) return normalized
  }
  return undefined
}

function firstString(...values: unknown[]): string | undefined {
  for (const value of values) {
    const normalized = stringValue(value)
    if (normalized !== undefined) return normalized
  }
  return undefined
}

/** Unknown states deliberately fail closed instead of being shown as healthy. */
export function normalizeAvailability(value: unknown): CapabilityAvailability {
  const state = stringValue(value)?.toLowerCase()
  if (!state) return 'unavailable'
  if (LIVE_STATES.has(state)) return 'live'
  if (PARTIAL_STATES.has(state)) return 'partial'
  if (UNAVAILABLE_STATES.has(state)) return 'unavailable'
  return 'unavailable'
}

function routeEvidence(record: UnknownRecord): CapabilityRouteEvidence {
  const route = nestedRecord(record, 'route')
  const routes = Array.isArray(record.routes)
    ? record.routes.filter(isRecord)
    : []
  const selectedRouteId = firstString(record.selected_route_id)
  const selected = routes.find(candidate => firstString(candidate.id) === selectedRouteId)
    ?? routes.find(candidate => {
      const probe = nestedRecord(candidate, 'probe')
      const credential = nestedRecord(candidate, 'credential')
      return candidate.configured === true
        && candidate.permitted === true
        && credential?.ready === true
        && probe?.state === 'succeeded'
        && probe?.fresh === true
    })
    ?? routes.find(candidate => candidate.configured === true && candidate.permitted === true)
    ?? routes[0]
  const probe = selected ? nestedRecord(selected, 'probe') : undefined
  const credential = selected ? nestedRecord(selected, 'credential') : undefined
  const status = firstString(
    route?.status,
    record.route_status,
    probe?.state,
  )
  const explicitHealthy = firstBoolean(
    route?.healthy,
    route?.available,
    record.route_healthy,
    record.route_available,
    record.healthy_route,
  )
  const canonicalHealthy = selected
    ? selected.configured === true
      && selected.permitted === true
      && credential?.ready === true
      && probe?.state === 'succeeded'
      && probe?.fresh === true
    : undefined

  return {
    id: firstString(selected?.id),
    healthy: explicitHealthy ?? canonicalHealthy ?? (status ? normalizeAvailability(status) === 'live' : undefined),
    status,
    provider: firstString(route?.provider, probe?.provider, record.provider),
    model: firstString(route?.model, probe?.model, record.model),
    configured: firstBoolean(selected?.configured),
    permitted: firstBoolean(selected?.permitted),
    credentialReady: firstBoolean(credential?.ready),
    probeState: firstString(probe?.state),
    probeFresh: firstBoolean(probe?.fresh),
  }
}

function rendererEvidence(record: UnknownRecord): CapabilityRendererEvidence {
  const renderer = nestedRecord(record, 'renderer')
  const status = firstString(
    renderer?.status,
    record.renderer_status,
  )
  const explicitAvailable = firstBoolean(
    renderer?.available,
    renderer?.implemented,
    record.renderer_available,
    record.renderer_implemented,
    record.has_renderer,
  )
  const required = firstBoolean(renderer?.required)
  const registered = firstBoolean(renderer?.registered)
  const healthy = firstBoolean(renderer?.healthy)

  return {
    available: explicitAvailable
      ?? (registered !== undefined
        ? registered === true && (required === false || healthy !== false)
        : status ? normalizeAvailability(status) === 'live' : undefined),
    id: firstString(renderer?.id, renderer?.name, record.renderer_id),
    status,
    required,
    registered,
    healthy,
  }
}

export function normalizeCapability(value: unknown): DiscoveredCapability | null {
  if (!isRecord(value)) return null

  const id = firstString(value.id, value.name)
  const name = firstString(value.name, value.title, value.id)
  if (!id || !name) return null

  const policy = nestedRecord(value, 'policy')
  const source = nestedRecord(value, 'source')
  const reason = nestedRecord(value, 'reason')

  return {
    id,
    name,
    description: firstString(value.description),
    kind: firstString(value.kind, value.type),
    availability: normalizeAvailability(value.status ?? value.availability),
    availabilityReason: firstString(value.availability_reason, reason?.message, value.reason),
    reasonCode: firstString(value.reason_code, reason?.code),
    invocable: firstBoolean(value.invocable, value.ui_invocable) === true,
    permitted: firstBoolean(value.permitted, value.policy_allowed, policy?.permitted, policy?.allowed),
    route: routeEvidence(value),
    renderer: rendererEvidence(value),
    sourceType: firstString(source?.type),
  }
}

function capabilityItems(payload: UnknownRecord): unknown[] | null {
  if (Array.isArray(payload.data)) return payload.data
  if (Array.isArray(payload.items)) return payload.items
  if (Array.isArray(payload.capabilities)) return payload.capabilities
  return null
}

function rollupAvailability(capabilities: DiscoveredCapability[]): CapabilityAvailability {
  if (!capabilities.length) return 'unavailable'
  const live = capabilities.filter((capability) => capability.availability === 'live').length
  const unavailable = capabilities.filter((capability) => capability.availability === 'unavailable').length
  if (live === capabilities.length) return 'live'
  if (unavailable === capabilities.length) return 'unavailable'
  return 'partial'
}

/** Pure, fail-closed normalization of the public capability contract. */
export function normalizeCapabilityCatalog(payload: unknown): CapabilityCatalog {
  const root = Array.isArray(payload) ? { data: payload } : payload
  if (!isRecord(root)) {
    return {
      availability: 'unavailable',
      capabilities: [],
      issue: { code: 'invalid_payload', message: 'Capability response is not an object or list.' },
    }
  }

  const items = capabilityItems(root)
  if (!items) {
    return {
      schemaVersion: stringValue(root.schema_version),
      availability: 'unavailable',
      capabilities: [],
      asOf: firstString(root.as_of, root.updated_at),
      issue: { code: 'invalid_payload', message: 'Capability response does not contain a capability list.' },
    }
  }

  const capabilities = items
    .map(normalizeCapability)
    .filter((capability): capability is DiscoveredCapability => capability !== null)
  const declaredStatus = firstString(root.status, root.availability)

  return {
    schemaVersion: stringValue(root.schema_version),
    availability: declaredStatus
      ? normalizeAvailability(declaredStatus)
      : rollupAvailability(capabilities),
    capabilities,
    asOf: firstString(root.as_of, root.updated_at),
  }
}

/**
 * A capability may enter the UI only when the backend says it is invocable and
 * live. Route, renderer, and policy evidence are required rather than inferred:
 * an advertised capability without a proved route cannot become a visible
 * control.
 */
export function isUiInvocableCapability(capability: DiscoveredCapability): boolean {
  return capability.invocable
    && capability.availability === 'live'
    && capability.route.healthy === true
    && capability.renderer.available === true
    && Boolean(capability.renderer.id)
    && capability.permitted === true
}

export function uiInvocableCapabilities(
  catalogOrCapabilities: CapabilityCatalog | readonly DiscoveredCapability[],
): DiscoveredCapability[] {
  const isCatalog = 'capabilities' in catalogOrCapabilities
  if (isCatalog && catalogOrCapabilities.availability === 'unavailable') return []

  const capabilities = isCatalog
    ? catalogOrCapabilities.capabilities
    : catalogOrCapabilities
  return capabilities.filter(isUiInvocableCapability)
}

export function findUiInvocableCapability(
  catalogOrCapabilities: CapabilityCatalog | readonly DiscoveredCapability[],
  id: string,
): DiscoveredCapability | undefined {
  return uiInvocableCapabilities(catalogOrCapabilities).find((capability) => capability.id === id)
}
