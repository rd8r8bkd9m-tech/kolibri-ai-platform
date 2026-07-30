import { useEffect, useRef, type ComponentType, type PointerEvent as ReactPointerEvent } from 'react'
import { createPortal } from 'react-dom'
import { X } from 'lucide-react'
import ToolListItem from './ToolListItem'
import ToolCarousel from './ToolCarousel'
import type { ComposerTool } from './composerTool'
import { shouldDismissToolSheetSwipe } from './toolSheetGesture'
import { useLocale } from '@/features/localization'

interface ToolSheetProps {
  open: boolean
  tools: ComposerTool[]
  onClose: () => void
  onTool: (key: ComposerTool['key']) => void
}

interface ToolDefinition {
  id: string
  title: string
  description: string
  icon: ComponentType<{ size?: number; strokeWidth?: number }>
  run: () => void
}

export default function ToolSheet({
  open,
  tools,
  onClose,
  onTool,
}: ToolSheetProps) {
  const { t } = useLocale()
  const dialogRef = useRef<HTMLElement>(null)
  const layerRef = useRef<HTMLDivElement>(null)
  const returnFocusRef = useRef<HTMLElement | null>(null)
  const swipeStartRef = useRef<number | null>(null)
  const onCloseRef = useRef(onClose)

  useEffect(() => { onCloseRef.current = onClose }, [onClose])

  useEffect(() => {
    if (!open) return
    returnFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const dialog = dialogRef.current
    const layer = layerRef.current
    if (!dialog || !layer) return
    const previousBodyOverflow = document.body.style.overflow
    const background = Array.from(document.body.children)
      .filter((child): child is HTMLElement => child instanceof HTMLElement && child !== layer)
      .map(element => ({
        element,
        inert: element.inert,
        ariaHidden: element.getAttribute('aria-hidden'),
      }))
    background.forEach(({ element }) => {
      element.inert = true
      element.setAttribute('aria-hidden', 'true')
    })
    document.body.style.overflow = 'hidden'
    window.requestAnimationFrame(() => dialog.querySelector<HTMLElement>('[data-tool-sheet-primary]')?.focus())
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        onCloseRef.current()
      }
      if (event.key !== 'Tab' || !dialog) return
      const focusable = Array.from(dialog.querySelectorAll<HTMLElement>('button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])'))
      const first = focusable[0]
      const last = focusable.at(-1)
      if (!first || !last) return
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      background.forEach(({ element, inert, ariaHidden }) => {
        element.inert = inert
        if (ariaHidden === null) element.removeAttribute('aria-hidden')
        else element.setAttribute('aria-hidden', ariaHidden)
      })
      document.body.style.overflow = previousBodyOverflow
      returnFocusRef.current?.focus()
    }
  }, [open])

  if (!open) return null

  const definitions: ToolDefinition[] = tools.map(item => ({
      id: item.key,
      title: item.title,
      description: item.description,
      icon: item.icon,
      run: () => onTool(item.key),
    }))
  const quickTools = definitions.slice(0, 4)
  const detailedTools = definitions.slice(4)

  const select = (tool: ToolDefinition) => {
    onClose()
    tool.run()
  }

  const beginEdgeSwipe = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (event.pointerType === 'mouse' && event.button !== 0) return
    swipeStartRef.current = event.clientY
    event.currentTarget.setPointerCapture(event.pointerId)
  }

  const finishEdgeSwipe = (event: ReactPointerEvent<HTMLDivElement>) => {
    const startY = swipeStartRef.current
    swipeStartRef.current = null
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId)
    if (startY !== null && shouldDismissToolSheetSwipe({ origin: 'edge', startY, endY: event.clientY })) onClose()
  }

  return createPortal(
    <div ref={layerRef} data-tool-sheet-layer="true" className="conversation-tool-sheet-layer md:hidden">
      <button type="button" className="conversation-tool-sheet-backdrop" aria-label={t('composer.closeTools')} onClick={onClose} />
      <section ref={dialogRef} className="conversation-tool-sheet" role="dialog" aria-modal="true" aria-label={t('composer.tools')}>
        <button type="button" className="conversation-tool-sheet-close" aria-label={t('composer.closeTools')} onClick={onClose}><X size={20} /></button>
        <div
          className="conversation-tool-sheet-swipe-edge"
          aria-hidden="true"
          onPointerDown={beginEdgeSwipe}
          onPointerUp={finishEdgeSwipe}
          onPointerCancel={() => { swipeStartRef.current = null }}
        >
          <div className="conversation-tool-sheet-handle" />
        </div>

        <div className="conversation-tool-sheet-scroll">
          <ToolCarousel
            label={t('tool.quickActions')}
            items={quickTools.map(tool => ({ id: tool.id, title: tool.title, icon: tool.icon }))}
            onSelect={id => {
              const tool = quickTools.find(item => item.id === id)
              if (tool) select(tool)
            }}
          />
          <div className="conversation-tool-list" aria-label={t('tool.available')}>
            {detailedTools.map(tool => (
              <ToolListItem
                key={tool.id}
                title={tool.title}
                description={tool.description}
                icon={tool.icon}
                onSelect={() => select(tool)}
              />
            ))}
            {!detailedTools.length && <p className="conversation-tool-list-hint">{t('tool.moreWhenAvailable')}</p>}
          </div>
        </div>
      </section>
    </div>,
    document.body,
  )
}
