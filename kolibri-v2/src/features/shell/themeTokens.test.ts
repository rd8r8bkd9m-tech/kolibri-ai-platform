/// <reference types="node" />

import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const css = readFileSync(new URL('../../index.css', import.meta.url), 'utf8')

describe('mobile conversation theme tokens', () => {
  it('keeps header controls readable in both light and dark themes', () => {
    expect(css).toContain('border: 1px solid color-mix(in srgb, var(--text-primary) 44%, transparent);')
    expect(css).toMatch(/\.shell-mobile-mode\s*\{[^}]*color:\s*var\(--text-primary\);/s)
    expect(css).toContain('.shell-mobile-mode span { color: var(--text-secondary);')
  })

  it('keeps mobile action buttons at the minimum accessible target size', () => {
    expect(css).toMatch(/\.shell-mobile-actions button\s*\{[^}]*width:\s*44px;[^}]*min-width:\s*44px;[^}]*height:\s*44px;[^}]*min-height:\s*44px;[^}]*flex:\s*0 0 44px;/s)
  })

  it('uses theme surfaces and inherited text for the mobile user bubble', () => {
    expect(css).toMatch(/\.conversation-message\.user\s*\{[^}]*background:\s*var\(--bg-elevated\);[^}]*color:\s*var\(--text-primary\);/s)
    expect(css).toContain('.conversation-message.user .conversation-message-content { color: inherit;')
    expect(css).not.toContain('background: #f0f0f0;')
  })
})
