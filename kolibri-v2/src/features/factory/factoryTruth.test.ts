import { describe, expect, it } from 'vitest'
import type { Node } from '@/lib/api'
import {
  evidenceLines,
  freshResourceNodes,
  nodeTruthBadges,
  summarizeNodes,
} from './factoryTruth'

function node(overrides: Partial<Node> = {}): Node {
  return {
    id: 'worker-01',
    name: 'worker-01',
    region: '',
    ip_address: '10.99.0.10',
    status: 'connected',
    connection: {
      status: 'online', connected: true, reported_health: 'online', source: 'node_health_report',
    },
    freshness: {
      status: 'fresh', fresh: true, heartbeat_at: '2026-07-14T00:00:00Z', heartbeat_age_seconds: 5,
    },
    execution: {
      status: 'ready', active: false, reported_active: false, active_task_id: null,
      executable: true, executable_capabilities: ['read_only_probe'], blocked: false,
      blocked_reasons: [], quarantined: false, quarantine_reason: null, schedulable: true,
    },
    verification: {
      status: 'unverified', verified: false, last_successful_task: null,
      source: 'home_control_plane_fleet_proof', as_of: '2026-07-14T00:00:00Z',
      reason: 'no_strict_verified_completion',
    },
    cpu_percent: '20',
    ram_percent: '30',
    disk_percent: '40',
    network_mbps: 'unavailable',
    agent_count: 1,
    task_count: 0,
    ping_ms: 5,
    max_agents: 1,
    capabilities: { items: ['read_only_probe'] },
    ...overrides,
  }
}

describe('factory truth presentation', () => {
  it('keeps membership, freshness, execution, activity and proof separate', () => {
    const membershipOnly = node({
      connection: { status: 'unknown', connected: false, reported_health: 'missing', source: 'node_health_report' },
      freshness: { status: 'stale', fresh: false, heartbeat_at: null, heartbeat_age_seconds: null },
      execution: {
        status: 'quarantined', active: false, reported_active: false, active_task_id: null,
        executable: false, executable_capabilities: [], blocked: false, blocked_reasons: [],
        quarantined: true, quarantine_reason: 'missing_registration', schedulable: false,
      },
    })
    const activeVerified = node({
      id: 'home',
      execution: {
        status: 'active', active: true, reported_active: true, active_task_id: 'TASK-1',
        executable: true, executable_capabilities: ['read_only_probe'], blocked: false,
        blocked_reasons: [], quarantined: false, quarantine_reason: null, schedulable: true,
      },
      verification: {
        status: 'verified', verified: true, source: 'home_control_plane_fleet_proof',
        as_of: '2026-07-14T00:00:00Z', reason: null,
        last_successful_task: {
          task_id: 'TASK-0', capability: 'read_only_probe', attempt_id: 'attempt-1',
          completed_at: '2026-07-13T23:59:00Z', result_sha256: 'a'.repeat(64),
          binding_sha256: 'b'.repeat(64), verifier: 'control-plane/home',
          verifier_schema: 'v1', evidence_source: '/v1/runtime/fleet-proof',
        },
      },
    })

    expect(summarizeNodes([membershipOnly, activeVerified])).toEqual({
      membership: 2,
      connected: 1,
      fresh: 1,
      executable: 1,
      active: 1,
      verified: 1,
      blocked: 0,
      quarantined: 1,
      stale: 1,
    })
    expect(freshResourceNodes([membershipOnly, activeVerified])).toEqual([activeVerified])
    expect(nodeTruthBadges(membershipOnly).map(item => item.key)).toContain('quarantined')
    expect(nodeTruthBadges(membershipOnly).map(item => item.key)).not.toContain('verified')
  })

  it('shows both result and binding digests from strict proof', () => {
    const proofNode = node({
      verification: {
        status: 'verified', verified: true, source: 'home_control_plane_fleet_proof',
        as_of: '2026-07-14T00:00:00Z', reason: null,
        last_successful_task: {
          task_id: 'TASK-1', capability: 'test', attempt_id: 'attempt-1', completed_at: null,
          result_sha256: `sha256:${'c'.repeat(64)}`, binding_sha256: 'd'.repeat(64),
          verifier: 'control-plane/home', verifier_schema: 'v1',
          evidence_source: '/v1/runtime/fleet-proof',
        },
      },
    })
    const lines = evidenceLines(proofNode.verification.last_successful_task)
    expect(lines).toHaveLength(2)
    expect(lines[0]).toMatchObject({ label: 'Результат', raw: `sha256:${'c'.repeat(64)}` })
    expect(lines[1]).toMatchObject({ label: 'Binding', raw: 'd'.repeat(64) })
  })
})
