import { describe, expect, it } from 'vitest'
import { capabilityIcons } from './capabilityIcons'
import type { UiCapabilityKey } from './types'

describe('capability icon registry', () => {
  it('covers every capability the Shell can expose on desktop and mobile', () => {
    const expected: UiCapabilityKey[] = [
      'estimate.create', 'document.editor',
      'web.search', 'file.search', 'document.pdf', 'document.docx', 'document.xlsx', 'document.pptx',
      'code.execute', 'image.generate', 'image.edit', 'site.create', 'app.create', 'browser.use', 'mcp.invoke',
    ]
    expect(Object.keys(capabilityIcons).sort()).toEqual(expected.sort())
    expected.forEach(key => expect(capabilityIcons[key]).toBeTypeOf('object'))
  })
})
