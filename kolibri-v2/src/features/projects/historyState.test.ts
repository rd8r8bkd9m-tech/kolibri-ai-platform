import { describe, expect, it } from 'vitest'
import type { Project, ProjectMessage } from '@/lib/api'
import { latestResponseId, removeProject, serverMessageStatus, sortProjects, upsertProject } from './historyState'

function project(id: string, updatedAt: string): Project {
  return {
    id,
    title: id,
    title_source: 'message',
    status: 'active',
    version: 1,
    message_count: 1,
    metadata: {},
    created_at: updatedAt,
    updated_at: updatedAt,
    last_message_at: updatedAt,
    deleted_at: null,
  }
}

describe('durable project history state', () => {
  it('sorts and upserts projects by server activity', () => {
    const old = project('old', '2026-07-13T10:00:00Z')
    const recent = project('recent', '2026-07-13T11:00:00Z')
    expect(sortProjects([old, recent]).map(item => item.id)).toEqual(['recent', 'old'])
    expect(upsertProject([old], recent).map(item => item.id)).toEqual(['recent', 'old'])
    expect(removeProject([recent, old], 'recent')).toEqual([old])
  })

  it('keeps pinned conversations above newer unpinned activity', () => {
    const pinned = { ...project('pinned', '2026-07-13T09:00:00Z'), metadata: { pinned: true } }
    const recent = project('recent', '2026-07-13T11:00:00Z')
    expect(sortProjects([recent, pinned]).map(item => item.id)).toEqual(['pinned', 'recent'])
  })

  it('maps persisted lifecycle and recovers the latest response id', () => {
    expect(serverMessageStatus('pending')).toBe('dispatching')
    expect(serverMessageStatus('streaming')).toBe('streaming')
    expect(serverMessageStatus('completed')).toBe('completed')
    const messages = [
      { metadata: {} },
      { metadata: { response_id: 'resp_1' } },
      { metadata: {} },
    ] as ProjectMessage[]
    expect(latestResponseId(messages)).toBe('resp_1')
  })
})
