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

  it.each(['developers', 'docs'])('keeps public /%s outside the private Shell rail', route => {
    const routeIndex = app.indexOf(`path="${route}"`)
    const boundaryIndex = app.indexOf('<Route element={<ShellBootstrapBoundary />}>')

    expect(routeIndex).toBeGreaterThan(-1)
    expect(routeIndex).toBeLessThan(boundaryIndex)
  })

  it('mounts /app through the canonical compatibility-aware Shell entry', () => {
    expect(app).toContain('path="app" element={<AppShellEntry />}')
    expect(layout).toContain("location.pathname.replace(/\\/+$/, '') === '/app'")
    expect(login).toContain("navigate('/app')")
  })

  it('offers a working password-recovery path from the login form', () => {
    expect(login).toContain('Забыли пароль?')
    expect(login).toContain('auth.requestPasswordReset')
    expect(login).toContain('auth.confirmPasswordReset')
    expect(login).not.toContain('t.me/kolibriai_bot')
    expect(login).toContain("setMode('recover')")
    expect(login).toContain('auth.requestPasswordReset(email)')
    expect(login).toContain('auth.confirmPasswordReset(resetToken, password)')
    expect(login).toContain('Назад ко входу')
  })

  it('does not mount the private layout before bootstrap succeeds', () => {
    expect(boundary).toContain('shell.bootstrap(attempt > 0)')
    expect(boundary).toContain("if (state === 'loading')")
    expect(boundary).toContain("if (state === 'error')")
    expect(boundary).toContain('return <Outlet />')
  })
})
