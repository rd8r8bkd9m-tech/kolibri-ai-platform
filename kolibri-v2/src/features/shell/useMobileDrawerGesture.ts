import { useRef, type PointerEvent } from 'react'

interface GestureOptions {
  open: boolean
  onOpen: () => void
  onClose: () => void
}

export default function useMobileDrawerGesture({ open, onOpen, onClose }: GestureOptions) {
  const start = useRef<{ x: number; y: number } | null>(null)

  return {
    onPointerDown: (event: PointerEvent) => {
      if (!open && event.clientX > 28) return
      start.current = { x: event.clientX, y: event.clientY }
    },
    onPointerUp: (event: PointerEvent) => {
      const origin = start.current
      start.current = null
      if (!origin) return
      const dx = event.clientX - origin.x
      const dy = event.clientY - origin.y
      if (Math.abs(dx) < 56 || Math.abs(dx) < Math.abs(dy) * 1.25) return
      if (!open && dx > 0) onOpen()
      if (open && dx < 0) onClose()
    },
  }
}
