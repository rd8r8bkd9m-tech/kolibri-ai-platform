import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const settings = readFileSync(new URL('../../pages/SettingsPage.tsx', import.meta.url), 'utf8')

describe('settings truth contract', () => {
  it('does not expose local-only notification or 2FA switches as completed account features', () => {
    expect(settings).not.toContain('kolibri-2fa')
    expect(settings).not.toContain('notif-push')
    expect(settings).not.toContain("id: 'notifications'")
  })

  it('does not offer guest-only API mutations and lists only implemented shortcuts', () => {
    expect(settings).toContain("!['security', 'organization'].includes(tab.id) || Boolean(user)")
    expect(settings).toContain('if (!user) return')
    expect(settings).not.toContain('settings.shortcutNewChat')
    expect(settings).not.toContain('settings.shortcutLibrary')
    expect(settings).not.toContain('settings.shortcutSettings')
  })
})
