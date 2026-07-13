export type ToolSheetGestureOrigin = 'edge' | 'content'

export interface ToolSheetSwipe {
  origin: ToolSheetGestureOrigin
  startY: number
  endY: number
}

export function shouldDismissToolSheetSwipe(
  swipe: ToolSheetSwipe,
  threshold = 72,
): boolean {
  return swipe.origin === 'edge' && swipe.endY - swipe.startY >= threshold
}
