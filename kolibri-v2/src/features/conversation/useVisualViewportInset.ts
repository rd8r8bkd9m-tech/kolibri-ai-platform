import { useEffect } from 'react'
import { getAdaptiveKeyboardInsetPx } from './composerRuntime'

export function useVisualViewportInset() {
  useEffect(() => {
    const viewport = window.visualViewport
    if (!viewport) return
    let animationFrame = 0

    const update = () => {
      if (animationFrame) return
      animationFrame = window.requestAnimationFrame(() => {
        animationFrame = 0
        const shellHeight = document.querySelector<HTMLElement>('.shell-root')?.getBoundingClientRect().height ?? null
        const inset = getAdaptiveKeyboardInsetPx(
          window.innerHeight,
          shellHeight,
          viewport.height,
          viewport.offsetTop,
        )
        document.documentElement.style.setProperty('--keyboard-inset', `${inset}px`)
      })
    }

    update()
    viewport.addEventListener('resize', update)
    viewport.addEventListener('scroll', update)
    window.addEventListener('resize', update)
    return () => {
      if (animationFrame) window.cancelAnimationFrame(animationFrame)
      viewport.removeEventListener('resize', update)
      viewport.removeEventListener('scroll', update)
      window.removeEventListener('resize', update)
      document.documentElement.style.removeProperty('--keyboard-inset')
    }
  }, [])
}
