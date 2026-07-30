import type { Agent, FactoryTaskEvidence, Node } from '@/lib/api'

export interface FactoryNodeSummary {
  membership: number
  connected: number
  fresh: number
  executable: number
  active: number
  verified: number
  blocked: number
  quarantined: number
  stale: number
}

export interface TruthBadge {
  key: string
  label: string
  tone: 'neutral' | 'info' | 'active' | 'verified' | 'warning' | 'danger'
}

export function summarizeNodes(nodes: Node[]): FactoryNodeSummary {
  return {
    membership: nodes.length,
    connected: nodes.filter(node => node.connection.connected).length,
    fresh: nodes.filter(node => node.freshness.fresh).length,
    executable: nodes.filter(node => node.execution.executable).length,
    active: nodes.filter(node => node.execution.active).length,
    verified: nodes.filter(node => node.verification.verified).length,
    blocked: nodes.filter(node => node.execution.blocked).length,
    quarantined: nodes.filter(node => node.execution.quarantined).length,
    stale: nodes.filter(node => node.freshness.status === 'stale').length,
  }
}

export function summarizeAgents(agents: Agent[]) {
  return {
    membership: agents.length,
    connected: agents.filter(agent => agent.connection.connected).length,
    fresh: agents.filter(agent => agent.freshness.fresh).length,
    executable: agents.filter(agent => agent.execution.executable).length,
    active: agents.filter(agent => agent.execution.active).length,
    verified: agents.filter(agent => agent.verification.verified).length,
  }
}

export function freshResourceNodes(nodes: Node[]): Node[] {
  return nodes.filter(node => node.connection.connected && node.freshness.fresh)
}

export function nodeTruthBadges(node: Node): TruthBadge[] {
  const badges: TruthBadge[] = []
  if (node.execution.quarantined) {
    badges.push({ key: 'quarantined', label: 'Карантин', tone: 'danger' })
  } else if (node.execution.blocked) {
    badges.push({ key: 'blocked', label: 'Заблокирован', tone: 'danger' })
  }
  badges.push(node.connection.connected
    ? { key: 'connected', label: 'Связь online', tone: 'info' }
    : { key: 'disconnected', label: 'Связь не доказана', tone: 'warning' })
  badges.push(node.freshness.fresh
    ? { key: 'fresh', label: 'Heartbeat свежий', tone: 'info' }
    : { key: 'stale', label: `Heartbeat: ${node.freshness.status}`, tone: 'warning' })
  if (node.execution.executable) {
    badges.push({ key: 'executable', label: 'Есть исполнимая capability', tone: 'active' })
  }
  if (node.execution.active) {
    badges.push({ key: 'active', label: 'Задача активна', tone: 'active' })
  }
  badges.push(node.verification.verified
    ? { key: 'verified', label: 'Результат проверен', tone: 'verified' }
    : {
        key: 'unverified',
        label: node.verification.status === 'unavailable'
          ? 'Проверка недоступна'
          : 'Нет проверенного результата',
        tone: 'neutral',
      })
  return badges
}

export function shortDigest(value: string | null | undefined): string {
  if (!value) return '—'
  const digest = value.startsWith('sha256:') ? value.slice(7) : value
  return digest.length > 16 ? `${digest.slice(0, 12)}…` : digest
}

export function evidenceLines(evidence: FactoryTaskEvidence | null): Array<{ label: string; value: string; raw: string }> {
  if (!evidence) return []
  return [
    { label: 'Результат', value: shortDigest(evidence.result_sha256), raw: evidence.result_sha256 },
    { label: 'Binding', value: shortDigest(evidence.binding_sha256), raw: evidence.binding_sha256 },
  ]
}
