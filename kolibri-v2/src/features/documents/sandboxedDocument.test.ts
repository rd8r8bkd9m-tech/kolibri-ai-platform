import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { sandboxedDocumentHtml } from './sandboxedDocument'

describe('sandboxed document source', () => {
  it('pins a deny-by-default CSP before untrusted content', () => {
    const value = sandboxedDocumentHtml('<img src=x onerror="alert(1)">')
    expect(value.indexOf('Content-Security-Policy')).toBeLessThan(value.indexOf('onerror'))
    expect(value).toContain("default-src 'none'")
    expect(value).toContain("form-action 'none'")
  })

  it('does not mount stored document HTML in the privileged parent DOM', () => {
    const documentsPage = readFileSync(new URL('../../pages/DocumentsPage.tsx', import.meta.url), 'utf8')
    const artifactCard = readFileSync(new URL('../conversation/ArtifactCard.tsx', import.meta.url), 'utf8')
    expect(documentsPage).not.toContain('dangerouslySetInnerHTML')
    expect(artifactCard).not.toContain('dangerouslySetInnerHTML')
    expect(documentsPage).toContain('sandbox=""')
    expect(artifactCard).toContain('sandbox=""')
  })
})
