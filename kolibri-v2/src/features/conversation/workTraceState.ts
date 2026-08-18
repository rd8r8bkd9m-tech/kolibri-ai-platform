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
  if (event.step_id) return `step:${event.step_id}`
  return [event.stage, normalized(event.provider), normalized(event.model)].join(':')
}

function durableEventIdentity(event: ChatWorkSummary): string | null {
  if (event.response_id && Number.isSafeInteger(event.sequence)) {
    return `${event.response_id}:${event.sequence}`
  }
  return null
}

function growingSummaryIdentity(event: ChatWorkSummary): string | null {
  return event.summary_id ? `${event.response_id ?? ''}:${event.summary_id}` : null
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
    event.summary_id ?? '',
    event.step_id ?? '',
    event.response_id ?? '',
    event.sequence?.toString() ?? '',
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
    const durableIdentity = durableEventIdentity(event)
    if (durableIdentity && current.some(candidate => durableEventIdentity(candidate) === durableIdentity)) {
      return current
    }
    const summaryIdentity = growingSummaryIdentity(event)
    if (summaryIdentity) {
      const previousIndex = current.findIndex(candidate => growingSummaryIdentity(candidate) === summaryIdentity)
      if (previousIndex >= 0) {
        const previous = current[previousIndex]
        if (
          Number.isSafeInteger(previous.sequence)
          && Number.isSafeInteger(event.sequence)
          && (previous.sequence as number) > (event.sequence as number)
        ) return current
        const next = [...current]
        next[previousIndex] = event
        return next
      }
    }
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
  return event.summary
}

export function shouldRenderWorkTrace(stage: string, expanded: boolean): boolean {
  void stage
  void expanded
  return true
}
