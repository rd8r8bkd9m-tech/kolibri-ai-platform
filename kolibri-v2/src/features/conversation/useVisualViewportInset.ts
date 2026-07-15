import { useEffect } from 'react'
import { getKeyboardInsetPx } from './composerRuntime'

export function useVisualViewportInset() {
  useEffect(() => {
    const viewport = window.visualViewport
    if (!viewport) return
    let animationFrame = 0

    const update = () => {
      if (animationFrame) return
      animationFrame = window.requestAnimationFrame(() => {
        animationFrame = 0
        const inset = getKeyboardInsetPx(window.innerHeight, viewport.height, viewport.offsetTop)
        document.documentElement.style.setProperty('--keyboard-inset', `${inset}px`)
      })
    }

    update()
    viewport.addEventListener('resize', update)
    viewport.addEventListener('scroll', update)
    return () => {
      if (animationFrame) window.cancelAnimationFrame(animationFrame)
      viewport.removeEventListener('resize', update)
      viewport.removeEventListener('scroll', update)
      document.documentElement.style.removeProperty('--keyboard-inset')
    }
  }, [])
}
