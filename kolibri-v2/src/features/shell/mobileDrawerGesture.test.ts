import { describe, expect, it } from 'vitest'
import { mobileDrawerGestureAction } from './mobileDrawerGesture'

describe('mobile navigation drawer gesture', () => {
  it('opens only from the mobile left edge', () => {
    expect(mobileDrawerGestureAction({ open: false, viewportWidth: 390, startX: 12, startY: 200, endX: 96, endY: 205 })).toBe('open')
    expect(mobileDrawerGestureAction({ open: false, viewportWidth: 390, startX: 42, startY: 200, endX: 126, endY: 205 })).toBe('none')
    expect(mobileDrawerGestureAction({ open: false, viewportWidth: 1024, startX: 12, startY: 200, endX: 96, endY: 205 })).toBe('none')
  })

  it('closes on a deliberate horizontal swipe and ignores scrolling', () => {
    expect(mobileDrawerGestureAction({ open: true, viewportWidth: 390, startX: 280, startY: 200, endX: 190, endY: 205 })).toBe('close')
    expect(mobileDrawerGestureAction({ open: true, viewportWidth: 390, startX: 280, startY: 200, endX: 235, endY: 310 })).toBe('none')
  })
})
