export interface MobileDrawerSwipe {
  open: boolean
  viewportWidth: number
  startX: number
  startY: number
  endX: number
  endY: number
}

export type MobileDrawerGestureAction = 'open' | 'close' | 'none'

/** Pure gesture contract shared by the shell and its tests. */
export function mobileDrawerGestureAction(
  swipe: MobileDrawerSwipe,
  edgeWidth = 28,
  distance = 56,
): MobileDrawerGestureAction {
  if (swipe.viewportWidth >= 768) return 'none'
  if (!swipe.open && swipe.startX > edgeWidth) return 'none'

  const dx = swipe.endX - swipe.startX
  const dy = swipe.endY - swipe.startY
  if (Math.abs(dx) < distance || Math.abs(dx) < Math.abs(dy) * 1.25) return 'none'
  if (!swipe.open && dx > 0) return 'open'
  if (swipe.open && dx < 0) return 'close'
  return 'none'
}
