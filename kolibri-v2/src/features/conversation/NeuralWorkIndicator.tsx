import type { ChatWorkStage, ChatWorkSummary } from '@/lib/api'

type WorkIndicatorState = 'idle' | 'connecting' | 'active' | 'waiting' | 'recovering' | 'completed' | 'failed' | 'cancelled'
type NodeState = 'future' | 'active' | 'completed' | 'failed'

interface NeuralWorkIndicatorProps {
  state: WorkIndicatorState
  events: ChatWorkSummary[]
  label: string
  latestSummary?: string
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

export default function NeuralWorkIndicator({ state, events, label, latestSummary }: NeuralWorkIndicatorProps) {
  const connecting = events.length === 0 && (state === 'connecting' || state === 'active' || state === 'recovering')
  const title = latestSummary || label

  return (
    <span
      className={`neural-work-indicator is-${connecting ? 'connecting' : 'staged'} state-${state}`}
      role="img"
      aria-label={label}
      title={title}
    >
      {connecting ? (
        <span className="neural-connection-dots" aria-hidden="true">
          <span />
          <span />
          <span />
        </span>
      ) : (
        <span className="neural-stage-nodes" aria-hidden="true">
          {nodeStates(events, state).map((nodeState, index) => (
            <span key={index} className={`neural-node is-${nodeState}`} />
          ))}
        </span>
      )}
    </span>
  )
}
