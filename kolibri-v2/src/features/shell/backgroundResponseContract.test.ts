/// <reference types="node" />

import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const app = readFileSync(new URL('../../App.tsx', import.meta.url), 'utf8')
const chat = readFileSync(new URL('../../pages/ChatPage.tsx', import.meta.url), 'utf8')
const status = readFileSync(new URL('./BackgroundResponseStatus.tsx', import.meta.url), 'utf8')
const styles = readFileSync(new URL('../../index.css', import.meta.url), 'utf8')

describe('background response UX contract', () => {
  it('keeps response work alive across ordinary SPA page unmounts', () => {
    expect(chat).not.toContain('useEffect(() => () => abortRef.current?.abort(), [])')
    expect(chat).not.toContain('abortRef.current?.abort()\n    activeAssistantRef.current = null')
    expect(chat).toContain('const ownsVisibleRequest = activeAssistantRef.current === assistantId')
    expect(chat).toContain('projectId: durableProject.id')
    expect(chat).toContain('outcome: activityOutcome')
  })

  it('mounts one global status and never asks for notification permission', () => {
    expect(app).toContain('<BackgroundResponseStatus />')
    expect(app.indexOf('<BackgroundResponseStatus />')).toBeLessThan(app.indexOf('<Routes>'))
    expect(status).toContain('Notification.permission')
    expect(status).not.toContain('requestPermission')
    expect(status).toContain('location.pathname !== `/chat/${encodeURIComponent(activity.projectId)}`')
    expect(status).toContain("latest?.summary || 'Kolibri отвечает'")
  })

  it('constrains long mobile traces and the estimate composer to the viewport', () => {
    expect(styles).toMatch(/\.work-trace\s*\{[^}]*width:\s*100%;[^}]*max-width:\s*100%;[^}]*min-width:\s*0;/s)
    expect(styles).toMatch(/\.work-trace-current\s*\{[^}]*flex:\s*1 1 auto;[^}]*min-width:\s*0;[^}]*max-width:\s*100%;[^}]*text-overflow:\s*ellipsis;[^}]*white-space:\s*nowrap;/s)
    expect(styles).toMatch(/\.work-trace-body li\s*\{[^}]*overflow-wrap:\s*anywhere;/s)
    expect(styles).toMatch(/\.estimate-command-composer\s*\{[^}]*grid-template-columns:\s*minmax\(0, 1fr\) 44px;/s)
    expect(styles).toMatch(/\.estimate-command-composer input\s*\{[^}]*width:\s*100%;[^}]*min-width:\s*0;/s)
    expect(styles).toMatch(/\.conversation-markdown-table-scroll\s*\{[^}]*max-width:\s*100%;[^}]*overflow-x:\s*auto;/s)
    expect(styles).toMatch(/@media \(max-width: 767px\)[\s\S]*\.conversation-dock\s*\{[^}]*position:\s*relative;[^}]*inset:\s*auto;/s)
  })
})
