import { normalizeCapabilityCatalog } from './normalize'
import type { CapabilityCatalog, CapabilityDiscoveryOptions } from './types'
import { resolveApiBase } from '@/lib/api'

function defaultCapabilitiesEndpoint(): string {
  const pathname = typeof window === 'undefined' ? undefined : window.location.pathname
  return `${resolveApiBase(pathname)}/capabilities`
}

function safeHttpMessage(status: number): string {
  return `Capability discovery returned HTTP ${status}.`
}

export async function discoverCapabilities(
  options: CapabilityDiscoveryOptions = {},
): Promise<CapabilityCatalog> {
  const fetchImpl = options.fetchImpl ?? fetch
  const endpoint = options.endpoint ?? defaultCapabilitiesEndpoint()

  try {
    const response = await fetchImpl(endpoint, {
      method: 'GET',
      credentials: 'same-origin',
      headers: { Accept: 'application/json' },
      signal: options.signal,
    })

    if (!response.ok) {
      return {
        availability: 'unavailable',
        capabilities: [],
        issue: {
          code: 'http_error',
          message: safeHttpMessage(response.status),
          status: response.status,
        },
      }
    }

    const contentType = response.headers.get('content-type')?.toLowerCase() ?? ''
    if (!contentType.includes('application/json') && !contentType.includes('+json')) {
      return {
        availability: 'unavailable',
        capabilities: [],
        issue: {
          code: 'invalid_payload',
          message: 'Capability discovery did not return JSON.',
          status: response.status,
        },
      }
    }

    return normalizeCapabilityCatalog(await response.json())
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error

    return {
      availability: 'unavailable',
      capabilities: [],
      issue: {
        code: 'network_error',
        message: 'Capability discovery is currently unreachable.',
      },
    }
  }
}
