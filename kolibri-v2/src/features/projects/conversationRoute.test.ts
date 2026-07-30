import { describe, expect, it } from 'vitest'
import { conversationRouteAction } from './conversationRoute'

describe('conversation route lifecycle', () => {
  it('preserves an optimistic first send on the initial new-chat route', () => {
    expect(conversationRouteAction(
      { initialized: false, projectId: null },
      null,
      null,
    )).toBe('preserve')
  })

  it('preserves the thread when the first send replaces the URL with its durable project id', () => {
    expect(conversationRouteAction(
      { initialized: true, projectId: null },
      'project_1',
      'project_1',
    )).toBe('preserve')
  })

  it('loads an existing project and resets only when explicitly starting a new chat', () => {
    expect(conversationRouteAction(
      { initialized: false, projectId: null },
      'project_1',
      null,
    )).toBe('load')
    expect(conversationRouteAction(
      { initialized: true, projectId: 'project_1' },
      null,
      null,
    )).toBe('reset')
  })
})
