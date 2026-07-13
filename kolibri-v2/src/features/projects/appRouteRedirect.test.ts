import { describe, expect, it } from 'vitest'
import { appRouteTarget } from './appRoute'

describe('/app compatibility route', () => {
  it('opens the requested project and preserves the complete query', () => {
    expect(appRouteTarget('?project=project_42&mode=deep')).toBe(
      '/chat/project_42?project=project_42&mode=deep',
    )
  })

  it('safely encodes a project id before placing it in the route', () => {
    expect(appRouteTarget('?project=project%2Flegacy')).toBe(
      '/chat/project%2Flegacy?project=project%2Flegacy',
    )
  })

  it('keeps query state when no project was supplied', () => {
    expect(appRouteTarget('?mode=fast')).toBe('/chat?mode=fast')
    expect(appRouteTarget('')).toBe('/chat')
  })
})
