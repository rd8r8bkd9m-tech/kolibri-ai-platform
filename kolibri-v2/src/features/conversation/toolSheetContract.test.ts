/// <reference types="node" />

import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const css = readFileSync(new URL('../../index.css', import.meta.url), 'utf8')
const component = readFileSync(new URL('./ToolSheet.tsx', import.meta.url), 'utf8')
const composer = readFileSync(new URL('./Composer.tsx', import.meta.url), 'utf8')
const composerRuntime = readFileSync(new URL('./composerRuntime.ts', import.meta.url), 'utf8')

describe('mobile tool sheet close contract', () => {
  it('keeps a labelled 44px close control above the scrollable carousel', () => {
    expect(component).toContain('className="conversation-tool-sheet-close"')
    expect(component).toContain("aria-label={t('composer.closeTools')}")
    expect(css).toMatch(/\.conversation-tool-sheet-close\s*\{[^}]*z-index:\s*4;[^}]*width:\s*44px;[^}]*height:\s*44px;[^}]*opacity:\s*1;[^}]*pointer-events:\s*auto;/s)
  })

  it('does not restore the invisible non-interactive close state', () => {
    expect(css).not.toMatch(/\.conversation-tool-sheet-close\s*\{[^}]*opacity:\s*0;[^}]*pointer-events:\s*none;/s)
  })
})

describe('mobile tool sheet capability truth', () => {
  it('contains no hard-coded estimate or document control outside the live capability list', () => {
    expect(component).not.toContain("id: 'estimate'")
    expect(component).not.toContain("id: 'document'")
    expect(component).not.toContain('onEstimate')
    expect(component).not.toContain('onDocument')
    expect(component).toContain('...capabilities.map')
  })

  it('hides the tool trigger and sheet when no backend capability is invocable', () => {
    expect(composer).toContain('const toolsAvailable = capabilities.length > 0')
    expect(composer).toContain('{toolsAvailable && <button')
    expect(composer).toContain('open={toolsOpen && isMobile && toolsAvailable}')
  })

  it('adds the second voice column only when a verified realtime control exists', () => {
    expect(css).toMatch(/\.conversation-composer\s*\{[^}]*grid-template-columns:\s*48px minmax\(0, 1fr\) 48px;/s)
    expect(css).toMatch(/\.conversation-composer:has\(\.composer-voice-mode-button\)\s*\{[^}]*48px minmax\(0, 1fr\) 48px 48px;/s)
    expect(composer).toContain('{voiceModeAvailable && <button')
  })

  it('keeps mobile safe-area and touch behavior wired without querying CSS env from JS', () => {
    expect(css).toContain('--safe-area-inset-bottom: env(safe-area-inset-bottom, 0px);')
    expect(css).toMatch(/\.conversation-dock\s*\{[^}]*var\(--safe-area-inset-bottom\)[^}]*var\(--keyboard-inset/s)
    expect(css).toMatch(/\.composer-tool-button,[^}]*touch-action:\s*manipulation;/s)
    expect(composerRuntime).not.toContain('getPropertyValue')
    expect(composerRuntime).not.toContain('env(safe-area-inset-bottom')
  })
})

describe('conversation scroll containment', () => {
  it('keeps the outer shell stationary while the message thread scrolls', () => {
    expect(css).toMatch(/\.conversation-page\s*\{[^}]*overflow:\s*clip;/s)
  })
})
