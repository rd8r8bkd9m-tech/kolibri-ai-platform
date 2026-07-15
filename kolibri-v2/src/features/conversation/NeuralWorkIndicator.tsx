import type { CSSProperties } from 'react'
import type { ChatWorkStage, ChatWorkSummary } from '@/lib/api'
import { NEURAL_NODE_LAYOUT } from './neuralWorkIndicatorLayout'

type WorkIndicatorState = 'idle' | 'connecting' | 'active' | 'waiting' | 'recovering' | 'completed' | 'failed' | 'cancelled'
type NodeState = 'future' | 'active' | 'completed' | 'failed'

interface NeuralWorkIndicatorProps {
  state: WorkIndicatorState
  events: ChatWorkSummary[]
  label: string
  latestSummary?: string
}

const STAGE_LABELS: Record<number, string> = {
  0: 'Понимаю запрос',
  1: 'Данные и источники',
  2: 'Инструменты и расчёты',
  3: 'Проверка',
  4: 'Ответ и артефакты',
}

const stageGroup: Record<ChatWorkStage, number> = {
  accepted: 0,
  planning: 0,
  reasoning_summary: 0,
  provider_route: 1,
  provider_attempt: 1,
  source_retrieval: 1,
  tool_execution: 2,
  calculation: 2,
  verification: 3,
  artifact_verification: 3,
  response_received: 4,
  artifact_materialization: 4,
  background: 0,
  resuming: 0,
  cancelled: 4,
}

function nodeStates(events: ChatWorkSummary[], state: WorkIndicatorState): NodeState[] {
  const nodes: NodeState[] = ['future', 'future', 'future', 'future', 'future']

  // First pass: collect raw states from events
  for (const event of events) {
    const index = stageGroup[event.stage]
    if (event.status === 'failed') nodes[index] = 'failed'
    else if (event.status === 'completed' && nodes[index] !== 'failed') nodes[index] = 'completed'
    else if (nodes[index] === 'future') nodes[index] = 'active'
  }

  // Second pass: find the highest active group index
  let highestActiveIndex = -1
  for (let i = nodes.length - 1; i >= 0; i--) {
    if (nodes[i] === 'active') {
      highestActiveIndex = i
      break
    }
  }

  // Third pass: only observed active groups before the highest active are complete.
  if (highestActiveIndex >= 0) {
    for (let i = 0; i < highestActiveIndex; i++) {
      if (nodes[i] === 'active') {
        nodes[i] = 'completed'
      }
    }
  }

  // Handle terminal states
  if (state === 'completed') nodes[4] = 'completed'
  if (state === 'failed' || state === 'cancelled') nodes[4] = 'failed'

  return nodes
}

function nodeLabel(nodeState: NodeState): string {
  if (nodeState === 'completed') return 'завершено'
  if (nodeState === 'active') return 'выполняется'
  if (nodeState === 'failed') return 'ошибка'
  return 'ожидание'
}

function buildTimelineDescription(nodes: NodeState[], state: WorkIndicatorState): string {
  const parts: string[] = []
  for (let i = 0; i < nodes.length; i++) {
    const nodeState = nodes[i]
    if (nodeState !== 'future') {
      parts.push(`${STAGE_LABELS[i]}: ${nodeLabel(nodeState)}`)
    }
  }
  if (state === 'completed') parts.push('Готово')
  else if (state === 'failed') parts.push('Ошибка')
  else if (state === 'cancelled') parts.push('Отменено')
  else if (state === 'waiting') parts.push('Ожидание')
  return parts.join(', ')
}

export default function NeuralWorkIndicator({ state, events, label, latestSummary }: NeuralWorkIndicatorProps) {
  const connecting = events.length === 0 && (state === 'connecting' || state === 'active' || state === 'recovering')
  const title = latestSummary || label
  const nodes = connecting ? null : nodeStates(events, state)
  const timelineDescription = nodes ? buildTimelineDescription(nodes, state) : ''
  const ariaLabel = connecting
    ? `${label}: подключение`
    : [label, timelineDescription].filter(Boolean).join(': ')

  if (connecting) {
    return (
      <span
        className={`neural-work-indicator is-connecting state-${state}`}
        role="status"
        aria-label={ariaLabel}
        title={title}
      >
        <span className="neural-connection-dots" aria-hidden="true">
          <span />
          <span />
          <span />
        </span>
      </span>
    )
  }

  return (
    <span
      className={`neural-work-indicator is-staged state-${state}`}
      title={title}
    >
      <span className="sr-only">{ariaLabel}</span>
      <span className="neural-stage-nodes is-circular" role="list" aria-label="Этапы выполнения">
        {nodes!.map((nodeState, index) => (
          <span
            key={index}
            className={`neural-node is-${nodeState}`}
            role="listitem"
            aria-label={`${STAGE_LABELS[index]}: ${nodeLabel(nodeState)}`}
            style={{
              '--neural-node-x': NEURAL_NODE_LAYOUT[index].x,
              '--neural-node-y': NEURAL_NODE_LAYOUT[index].y,
            } as CSSProperties}
          />
        ))}
      </span>
    </span>
  )
}
