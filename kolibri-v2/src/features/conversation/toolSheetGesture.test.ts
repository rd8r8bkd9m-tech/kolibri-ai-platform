import { describe, expect, it } from 'vitest'
import { shouldDismissToolSheetSwipe } from './toolSheetGesture'

describe('mobile tool sheet swipe contract', () => {
  it('dismisses only a deliberate downward swipe starting at the sheet edge', () => {
    expect(shouldDismissToolSheetSwipe({ origin: 'edge', startY: 100, endY: 172 })).toBe(true)
    expect(shouldDismissToolSheetSwipe({ origin: 'edge', startY: 100, endY: 171 })).toBe(false)
    expect(shouldDismissToolSheetSwipe({ origin: 'edge', startY: 180, endY: 90 })).toBe(false)
  })

  it('never treats internal content scrolling as a dismiss gesture', () => {
    expect(shouldDismissToolSheetSwipe({ origin: 'content', startY: 100, endY: 500 })).toBe(false)
  })
})
