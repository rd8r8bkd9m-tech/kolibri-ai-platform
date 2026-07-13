import type { ComponentType } from 'react'

export interface ToolCarouselItem {
  id: string
  title: string
  icon: ComponentType<{ size?: number; strokeWidth?: number }>
}

interface ToolCarouselProps {
  items: ToolCarouselItem[]
  onSelect: (id: string) => void
}

export default function ToolCarousel({ items, onSelect }: ToolCarouselProps) {
  return (
    <div className="conversation-tool-carousel" role="list" aria-label="Быстрые действия">
      {items.map(item => {
        const Icon = item.icon
        return (
          <button key={item.id} type="button" role="listitem" onClick={() => onSelect(item.id)}>
            <Icon size={27} strokeWidth={1.8} />
            <strong>{item.title}</strong>
          </button>
        )
      })}
    </div>
  )
}
