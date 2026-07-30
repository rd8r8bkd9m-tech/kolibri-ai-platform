/// <reference types="node" />

import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const settings = readFileSync(new URL('../../pages/SettingsPage.tsx', import.meta.url), 'utf8')
const billing = readFileSync(new URL('../billing/BillingSettings.tsx', import.meta.url), 'utf8')
const styles = readFileSync(new URL('../../index.css', import.meta.url), 'utf8')

describe('quiet settings visual contract', () => {
  it('uses the shared settings shell and exposes billing only to signed-in users', () => {
    expect(settings).toContain('className="settings-page"')
    expect(settings).toContain('className="settings-layout"')
    expect(settings).toContain("['security', 'organization', 'billing']")
    expect(settings).toContain("activeTab === 'billing' && user")
  })

  it('renders honest disabled provider states instead of a fake checkout', () => {
    expect(billing).toContain('data-billing-placeholder')
    expect(billing).toContain('Списания не выполняются')
    expect(billing).toContain('Настройка недоступна')
    expect(billing).toContain('disabled aria-disabled="true"')
    expect(billing).not.toMatch(/apiKey|secret|terminalKey|shopId|checkoutUrl/)
  })

  it('has explicit mobile layouts for navigation, provider rows and pricing', () => {
    expect(styles).toContain('.settings-navigation > div { display: none; }')
    expect(styles).toContain('.settings-mobile-section-picker { display: grid;')
    expect(settings).toContain('className="settings-mobile-section-picker"')
    expect(styles).toContain('.settings-provider-row { grid-template-columns: 42px minmax(0, 1fr);')
    expect(styles).toContain('.public-pricing-teaser-plans { grid-template-columns: 1fr; }')
  })
})
