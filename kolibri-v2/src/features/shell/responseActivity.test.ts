import { describe, expect, it } from 'vitest'
import {
  completionNotificationPayload,
  updateActiveResponseActivities,
  updateActiveResponseIds,
} from './responseActivity'

describe('durable response activity', () => {
  it('keeps reload blocked until every overlapping response has settled', () => {
    let active = updateActiveResponseIds(new Set(), { id: 'response-a', active: true })
    active = updateActiveResponseIds(active, { id: 'response-b', active: true })
    active = updateActiveResponseIds(active, { id: 'response-a', active: false })

    expect([...active]).toEqual(['response-b'])

    active = updateActiveResponseIds(active, { id: 'response-b', active: false })
    expect(active.size).toBe(0)
  })

  it('ignores malformed lifecycle events instead of releasing another response', () => {
    const active = new Set(['response-a'])
    expect(updateActiveResponseIds(active, { active: false })).toEqual(active)
    expect(updateActiveResponseIds(active, { id: '', active: false })).toEqual(active)
  })

  it('retains project metadata across progress events and removes only the completed task', () => {
    let active = updateActiveResponseActivities(new Map(), {
      id: 'response-a',
      active: true,
      projectId: 'project-a',
      startedAt: 100,
      summary: 'Задача принята фабрикой',
    })
    active = updateActiveResponseActivities(active, {
      id: 'response-a',
      active: true,
      summary: 'Проверяется результат',
    })
    active = updateActiveResponseActivities(active, { id: 'response-b', active: true, startedAt: 200 })

    expect(active.get('response-a')).toEqual({
      id: 'response-a',
      projectId: 'project-a',
      startedAt: 100,
      summary: 'Проверяется результат',
    })
    active = updateActiveResponseActivities(active, { id: 'response-a', active: false, outcome: 'completed' })
    expect([...active.keys()]).toEqual(['response-b'])
  })

  it('creates completion notifications only for an already granted permission', () => {
    const completed = { id: 'response-a', active: false, outcome: 'completed' as const }
    expect(completionNotificationPayload(completed, 'granted')).toMatchObject({
      title: 'Kolibri — ответ готов',
      options: { tag: 'kolibri-response-response-a' },
    })
    expect(completionNotificationPayload(completed, 'default')).toBeNull()
    expect(completionNotificationPayload(completed, 'denied')).toBeNull()
    expect(completionNotificationPayload({ ...completed, outcome: 'failed' }, 'granted')).toBeNull()
  })
})
