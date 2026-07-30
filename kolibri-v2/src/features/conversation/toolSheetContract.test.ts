/// <reference types="node" />

import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const css = readFileSync(new URL('../../index.css', import.meta.url), 'utf8')
const component = readFileSync(new URL('./ToolSheet.tsx', import.meta.url), 'utf8')
const composer = readFileSync(new URL('./Composer.tsx', import.meta.url), 'utf8')
const composerRuntime = readFileSync(new URL('./composerRuntime.ts', import.meta.url), 'utf8')
const chatPage = readFileSync(new URL('../../pages/ChatPage.tsx', import.meta.url), 'utf8')

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
    expect(component).toContain('tools.map')
  })

  it('hides the tool trigger and sheet only when neither live nor fallback tools exist', () => {
    expect(composer).toContain('const toolsAvailable = resolvedTools.length > 0')
    expect(composer).toContain('const toolButtonAvailable = toolsAvailable || Boolean(onAttach)')
    expect(composer).toContain('{toolButtonAvailable && <button')
    expect(composer).toContain('else onAttach?.()')
    expect(composer).toContain('open={toolsOpen && isMobile && toolsAvailable}')
  })

  it('keeps the three core App tools visible while capability discovery is empty', () => {
    expect(chatPage).toContain('const fallbackComposerTools: ComposerTool[] = [')
    expect(chatPage).toContain("key: 'estimate.create'")
    expect(chatPage).toContain("key: 'file.search'")
    expect(chatPage).toContain("key: 'web.search'")
    expect(chatPage).toContain('const composerTools: ComposerTool[] = capabilityMenu.length > 0')
    expect(chatPage).toContain(': fallbackComposerTools')
    expect(chatPage).toContain('tools={composerTools}')
  })

  it('adds the second voice column only when a verified realtime control exists', () => {
    expect(css).toMatch(/\.conversation-composer\s*\{[^}]*grid-template-columns:\s*48px minmax\(0, 1fr\) 48px;/s)
    expect(css).toMatch(/\.conversation-composer:has\(\.composer-voice-mode-button\)\s*\{[^}]*48px minmax\(0, 1fr\) 48px 48px;/s)
    expect(composer).toContain('{voiceModeAvailable && <button')
  })

  it('replaces send with an accessible stop control while a response is running', () => {
    expect(composer).toContain('{busy && onCancel ? <button')
    expect(composer).toContain("aria-label={t('composer.stop')}")
    expect(composer).toContain('<Square size={17} fill="currentColor"')
    expect(composer).toContain('onClick={onCancel}')
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
