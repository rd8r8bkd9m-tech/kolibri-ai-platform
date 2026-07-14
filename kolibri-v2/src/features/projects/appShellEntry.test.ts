import { describe, expect, it } from 'vitest'
import { shouldRedirectAppEntry } from './appShellEntry'

describe('/app shell entry', () => {
  it('keeps the canonical empty shell on /app', () => {
    expect(shouldRedirectAppEntry('', '')).toBe(false)
  })

  it.each([
    ['?project=project_42', ''],
    ['?q=%D0%BF%D1%80%D0%B8%D0%B2%D0%B5%D1%82', ''],
    ['?mode=deep', ''],
    ['', '#handoff=handoff-token'],
  ])('hands compatibility state to the redirect flow for %s%s', (search, hash) => {
    expect(shouldRedirectAppEntry(search, hash)).toBe(true)
  })
})
