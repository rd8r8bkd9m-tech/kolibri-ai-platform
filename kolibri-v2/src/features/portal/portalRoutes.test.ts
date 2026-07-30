import { describe, expect, it } from 'vitest'
import { PUBLIC_PORTAL_PATHS, isPrivatePortalPath, resolvePortalRouteMeta } from './portalRoutes'

describe('public portal route metadata', () => {
  it.each(['/', '/pricing', '/security', '/privacy', '/terms', '/developers', '/docs'])('publishes canonical index metadata for %s', path => {
    const meta = resolvePortalRouteMeta(path)
    expect(PUBLIC_PORTAL_PATHS).toContain(path)
    expect(meta.robots).toBe('index, follow')
    expect(meta.canonical).toBe(`https://kolibriai.ru${path}`)
    expect(meta.title).toContain('Kolibri')
    expect(meta.description.length).toBeGreaterThan(30)
  })

  it.each(['/app', '/app/project/one', '/chat/project_1', '/settings', '/control'])('keeps private routes out of the index for %s', path => {
    expect(isPrivatePortalPath(path)).toBe(true)
    expect(resolvePortalRouteMeta(path)).toMatchObject({ robots: 'noindex, nofollow', canonical: null })
  })

  it('does not accidentally index an unknown SPA route', () => {
    expect(resolvePortalRouteMeta('/missing')).toMatchObject({ robots: 'noindex, nofollow', canonical: null })
  })
})
