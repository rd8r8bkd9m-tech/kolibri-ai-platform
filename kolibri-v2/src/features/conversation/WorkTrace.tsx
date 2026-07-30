import { ChevronDown } from 'lucide-react'
import { useState } from 'react'
import type { ChatWorkSummary } from '@/lib/api'
import NeuralWorkIndicator from './NeuralWorkIndicator'
import { dedupeWorkSummaries, shouldRenderWorkTrace, workSummaryLabel } from './workTraceState'
import { translateKnownTraceSummary, useLocale, type TranslationKey } from '@/features/localization'

export type WorkStage = 'dispatching' | 'streaming' | 'waiting' | 'recovering' | 'completed' | 'failed' | 'cancelled'

interface WorkTraceProps {
  stage: WorkStage
  elapsedSeconds: number
  events: ChatWorkSummary[]
}

const stageCopy: Record<WorkStage, TranslationKey> = {
  dispatching: 'trace.dispatching',
  streaming: 'trace.streaming',
  waiting: 'trace.waiting',
  recovering: 'trace.recovering',
  completed: 'trace.completed',
  failed: 'trace.failed',
  cancelled: 'trace.cancelled',
}

function indicatorState(stage: WorkStage) {
  if (stage === 'dispatching') return 'connecting' as const
  if (stage === 'streaming') return 'active' as const
  return stage
}

export default function WorkTrace({ stage, elapsedSeconds, events }: WorkTraceProps) {
  const { locale, t } = useLocale()
  const [expanded, setExpanded] = useState(false)
  const visibleEvents = dedupeWorkSummaries(events)
  const localizedEvents = visibleEvents.map(event => ({
    ...event,
    summary: translateKnownTraceSummary(locale, event.summary),
  }))
  const latest = localizedEvents.at(-1)
  const currentSummary = latest ? workSummaryLabel(latest) : t(stageCopy[stage])
  const completedSummary = `${t('trace.worked', { count: elapsedSeconds })} · ${t('trace.steps', { count: localizedEvents.length })}`
  const summary = stage === 'completed' ? completedSummary : currentSummary

  if (!shouldRenderWorkTrace(stage, expanded)) return null

  return (
    <details className={`work-trace ${stage}`} open={expanded} onToggle={event => setExpanded(event.currentTarget.open)}>
      <summary title={currentSummary} aria-label={`${t('trace.title')}: ${summary}`}>
        <NeuralWorkIndicator
          state={indicatorState(stage)}
          events={localizedEvents}
          label={`${t('trace.title')}: ${summary}`}
          latestSummary={currentSummary}
        />
        <span className="work-trace-current" aria-live="polite" aria-atomic="true">{summary}</span>
        <span className="work-trace-title">{t('trace.title')}</span>
        <ChevronDown size={16} className="work-trace-chevron" />
      </summary>
      {localizedEvents.length > 0 && (
        <div className="work-trace-body">
          <strong>{t('trace.excerpts')}</strong>
          <ol>
            {localizedEvents.map((event, index) => (
              <li
                key={event.summary_id ?? event.step_id ?? `${event.stage}-${event.status}-${event.sequence ?? index}`}
                className={event.status === 'completed' ? 'done' : event.status}
              >
                {workSummaryLabel(event)}
              </li>
            ))}
          </ol>
        </div>
      )}
    </details>
  )
}
