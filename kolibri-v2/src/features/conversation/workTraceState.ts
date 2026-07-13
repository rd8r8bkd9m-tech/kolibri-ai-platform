import type { ChatWorkSummary } from '@/lib/api'

const ROUTE_STAGES = new Set<ChatWorkSummary['stage']>([
  'accepted',
  'provider_route',
  'provider_attempt',
  'response_received',
])

function normalized(value: string | undefined): string {
  return value?.trim().toLocaleLowerCase('ru-RU') ?? ''
}

function routeIdentity(event: ChatWorkSummary): string | null {
  if (!ROUTE_STAGES.has(event.stage)) return null
  if (event.stage === 'accepted') return 'accepted'
  return [event.stage, normalized(event.provider), normalized(event.model)].join(':')
}

function exactIdentity(event: ChatWorkSummary): string {
  return [
    event.stage,
    event.status,
    normalized(event.summary),
    normalized(event.provider),
    normalized(event.model),
    normalized(event.artifact_type),
    normalized(event.artifact_id),
  ].join(':')
}

function sameEvent(left: ChatWorkSummary, right: ChatWorkSummary): boolean {
  return exactIdentity(left) === exactIdentity(right)
}

/**
 * Keeps the public work trace compact. Accepted and provider lifecycle updates
 * replace the earlier state for the same route; exact tool/artifact events are
 * shown once even if a resumed stream replays them.
 */
export function dedupeWorkSummaries(events: ChatWorkSummary[]): ChatWorkSummary[] {
  return events.reduce<ChatWorkSummary[]>((current, event) => {
    const identity = routeIdentity(event)
    if (identity) {
      const previousIndex = current.findIndex(candidate => routeIdentity(candidate) === identity)
      if (previousIndex >= 0) {
        if (sameEvent(current[previousIndex], event)) return current
        const next = [...current]
        next[previousIndex] = event
        return next
      }
    } else if (current.some(candidate => sameEvent(candidate, event))) {
      return current
    }
    return [...current, event]
  }, [])
}

export function workSummaryLabel(event: ChatWorkSummary): string {
  const provenance = [event.provider, event.model]
    .map(value => value?.trim())
    .filter((value): value is string => Boolean(value))
    .filter((value, index, values) => values.findIndex(candidate => normalized(candidate) === normalized(value)) === index)

  return provenance.length > 0 ? `${event.summary} · ${provenance.join(' · ')}` : event.summary
}

export function shouldRenderWorkTrace(stage: string, expanded: boolean): boolean {
  return stage !== 'completed' || expanded
}
