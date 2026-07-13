import { describe, expect, it } from 'vitest'
import { updateActiveResponseIds } from './responseActivity'

describe('durable response activity', () => {
  it('keeps reload blocked until every overlapping response has settled', () => {
    let active = updateActiveResponseIds(new Set(), { id: 'response-a', active: true })
    active = updateActiveResponseIds(active, { id: 'response-b', active: true })
    active = updateActiveResponseIds(active, { id: 'response-a', active: false })

    expect([...active]).toEqual(['response-b'])

    active = updateActiveResponseIds(active, { id: 'response-b', active: false })
    expect(active.size).toBe(0)
  })

  it('ignores malformed lifecycle events instead of releasing another response', () => {
    const active = new Set(['response-a'])
    expect(updateActiveResponseIds(active, { active: false })).toEqual(active)
    expect(updateActiveResponseIds(active, { id: '', active: false })).toEqual(active)
  })
})
