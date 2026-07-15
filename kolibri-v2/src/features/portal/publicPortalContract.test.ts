/// <reference types="node" />

import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const app = readFileSync(new URL('../../App.tsx', import.meta.url), 'utf8')
const landing = readFileSync(new URL('../../pages/PublicLanding.tsx', import.meta.url), 'utf8')
const robots = readFileSync(new URL('../../../public/robots.txt', import.meta.url), 'utf8')
const sitemap = readFileSync(new URL('../../../public/sitemap.xml', import.meta.url), 'utf8')
const nginx = readFileSync(new URL('../../../nginx.conf', import.meta.url), 'utf8')

describe('public portal release contract', () => {
  it.each(['pricing', 'security', 'privacy', 'terms'])('mounts /%s outside the shell bootstrap boundary', route => {
    const routeIndex = app.indexOf(`path="${route}"`)
    const boundaryIndex = app.indexOf('<Route element={<ShellBootstrapBoundary />}>')
    expect(routeIndex).toBeGreaterThan(-1)
    expect(routeIndex).toBeLessThan(boundaryIndex)
  })

  it('keeps the public landing independent from private API data', () => {
    expect(landing).not.toContain("from '@/lib/api'")
    expect(landing).not.toMatch(/project_id|workspace_id|access_token|user\.name/)
  })

  it('excludes application routes from robots and sitemap', () => {
    for (const path of ['/app', '/chat', '/settings', '/control']) {
      expect(robots).toContain(`Disallow: ${path}`)
      expect(sitemap).not.toContain(`<loc>https://kolibriai.ru${path}`)
    }
    for (const path of ['/', '/pricing', '/security', '/privacy', '/terms']) {
      expect(sitemap).toContain(`<loc>https://kolibriai.ru${path}</loc>`)
    }
  })

  it('adds an HTTP noindex header to private SPA routes', () => {
    expect(nginx).toContain('location ~ ^/(app|chat|library|apps|estimates|documents|agents|control|servers|settings|login|playground|share)(/|$)')
    expect(nginx).toContain('add_header X-Robots-Tag "noindex, nofollow, noarchive" always;')
  })
})
