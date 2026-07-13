/// <reference types="node" />

import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const css = readFileSync(new URL('../../index.css', import.meta.url), 'utf8')
const component = readFileSync(new URL('./ToolSheet.tsx', import.meta.url), 'utf8')

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
