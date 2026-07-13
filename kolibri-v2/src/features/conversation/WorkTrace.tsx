import { CheckCircle2, ChevronDown, CircleAlert, LoaderCircle } from 'lucide-react'
import { useState } from 'react'
import type { ChatWorkSummary } from '@/lib/api'
import { dedupeWorkSummaries, shouldRenderWorkTrace, workSummaryLabel } from './workTraceState'
import { translateKnownTraceSummary, useLocale, type TranslationKey } from '@/features/localization'

export type WorkStage = 'dispatching' | 'streaming' | 'completed' | 'failed' | 'cancelled'

interface WorkTraceProps {
  stage: WorkStage
  elapsedSeconds: number
  events: ChatWorkSummary[]
}

const stageCopy: Record<WorkStage, TranslationKey> = {
  dispatching: 'trace.dispatching',
  streaming: 'trace.streaming',
  completed: 'trace.completed',
  failed: 'trace.failed',
  cancelled: 'trace.cancelled',
}

export default function WorkTrace({ stage, elapsedSeconds, events }: WorkTraceProps) {
  const { locale, t } = useLocale()
  const pending = stage === 'dispatching' || stage === 'streaming'
  const [expanded, setExpanded] = useState(false)
  const visibleEvents = dedupeWorkSummaries(events)
  const localizedEvents = visibleEvents.map(event => ({
    ...event,
    summary: translateKnownTraceSummary(locale, event.summary),
  }))
  const latest = localizedEvents.at(-1)
  const summary = latest ? workSummaryLabel(latest) : t(stageCopy[stage])
  const StatusIcon = pending ? LoaderCircle : stage === 'failed' || stage === 'cancelled' ? CircleAlert : CheckCircle2

  if (!shouldRenderWorkTrace(stage, expanded)) return null

  return (
    <details className={`work-trace ${stage}`} open={expanded} onToggle={event => setExpanded(event.currentTarget.open)}>
      <summary>
        <StatusIcon size={17} className={pending ? 'animate-spin' : undefined} />
        <span className="work-trace-current">{summary}</span>
        <span className="ml-auto tabular-nums text-[var(--text-tertiary)]">{t('trace.seconds', { count: elapsedSeconds })}</span>
        {localizedEvents.length > 0 && <ChevronDown size={16} className="work-trace-chevron" />}
      </summary>
      {localizedEvents.length > 0 && (
        <div className="work-trace-body">
          {localizedEvents.map((event, index) => (
            <span key={`${event.stage}-${event.status}-${event.provider ?? ''}-${event.model ?? ''}-${index}`} className={event.status === 'completed' ? 'done' : event.status}>
              {workSummaryLabel(event)}
            </span>
          ))}
        </div>
      )}
    </details>
  )
}
