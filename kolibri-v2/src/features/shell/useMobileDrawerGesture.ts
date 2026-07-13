import { useRef, type PointerEvent } from 'react'
import { mobileDrawerGestureAction } from './mobileDrawerGesture'

interface GestureOptions {
  open: boolean
  onOpen: () => void
  onClose: () => void
}

export default function useMobileDrawerGesture({ open, onOpen, onClose }: GestureOptions) {
  const start = useRef<{ x: number; y: number } | null>(null)

  return {
    onPointerDown: (event: PointerEvent) => {
      if (window.innerWidth >= 768 || (!open && event.clientX > 28)) return
      start.current = { x: event.clientX, y: event.clientY }
    },
    onPointerUp: (event: PointerEvent) => {
      const origin = start.current
      start.current = null
      if (!origin) return
      const action = mobileDrawerGestureAction({
        open,
        viewportWidth: window.innerWidth,
        startX: origin.x,
        startY: origin.y,
        endX: event.clientX,
        endY: event.clientY,
      })
      if (action === 'open') onOpen()
      if (action === 'close') onClose()
    },
    onPointerCancel: () => { start.current = null },
  }
}
