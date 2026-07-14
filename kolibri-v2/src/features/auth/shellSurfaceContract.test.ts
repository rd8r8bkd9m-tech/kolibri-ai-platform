/// <reference types="node" />

import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const app = readFileSync(new URL('../../App.tsx', import.meta.url), 'utf8')
const boundary = readFileSync(new URL('./ShellBootstrapBoundary.tsx', import.meta.url), 'utf8')
const layout = readFileSync(new URL('../../components/Layout.tsx', import.meta.url), 'utf8')
const login = readFileSync(new URL('../../pages/LoginPage.tsx', import.meta.url), 'utf8')

describe('public portal and protected Shell route contract', () => {
  it('keeps the indexable landing outside the session bootstrap boundary', () => {
    const landingIndex = app.indexOf('<Route index element={<ErrorBoundary><PublicLanding /></ErrorBoundary>} />')
    const boundaryIndex = app.indexOf('<Route element={<ShellBootstrapBoundary />}>')

    expect(landingIndex).toBeGreaterThan(-1)
    expect(boundaryIndex).toBeGreaterThan(landingIndex)
  })

  it('mounts /app through the canonical compatibility-aware Shell entry', () => {
    expect(app).toContain('path="app" element={<AppShellEntry />}')
    expect(layout).toContain("location.pathname.replace(/\\/+$/, '') === '/app'")
    expect(login).toContain("navigate('/app')")
  })

  it('does not mount the private layout before bootstrap succeeds', () => {
    expect(boundary).toContain('shell.bootstrap(attempt > 0)')
    expect(boundary).toContain("if (state === 'loading')")
    expect(boundary).toContain("if (state === 'error')")
    expect(boundary).toContain('return <Outlet />')
  })
})
