/// <reference types="node" />

import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const app = readFileSync(new URL('../../App.tsx', import.meta.url), 'utf8')
const layout = readFileSync(new URL('../../components/Layout.tsx', import.meta.url), 'utf8')
const chat = readFileSync(new URL('../../pages/ChatPage.tsx', import.meta.url), 'utf8')

describe('release update lifecycle contract', () => {
  it('keeps the controller alive above login, routes, and the shell error boundary', () => {
    expect(app).toContain('<ReleaseUpdateController />')
    expect(app.indexOf('<ReleaseUpdateController />')).toBeLessThan(app.indexOf('<Routes>'))
    expect(layout).not.toContain('ReleaseUpdateController')
  })

  it('releases response activity only after the durable patch queue settles', () => {
    expect(chat).toMatch(/finally\s*\{\s*await patchQueue\s*dispatchResponseActivity\(assistantId, false, \{/)
    expect(chat).not.toContain("new CustomEvent('kolibri:response-active'")
  })
})
