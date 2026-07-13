import type { ComponentType } from 'react'

export interface ToolCarouselItem {
  id: string
  title: string
  icon: ComponentType<{ size?: number; strokeWidth?: number }>
}

interface ToolCarouselProps {
  items: ToolCarouselItem[]
  onSelect: (id: string) => void
  label: string
}

export default function ToolCarousel({ items, onSelect, label }: ToolCarouselProps) {
  return (
    <div className="conversation-tool-carousel" role="group" aria-label={label}>
      {items.map(item => {
        const Icon = item.icon
        return (
          <button key={item.id} type="button" data-tool-sheet-primary={item.id} onClick={() => onSelect(item.id)}>
            <Icon size={27} strokeWidth={1.8} />
            <strong>{item.title}</strong>
          </button>
        )
      })}
    </div>
  )
}
