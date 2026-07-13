import type { ComponentType } from 'react'

interface ToolListItemProps {
  title: string
  description: string
  icon: ComponentType<{ size?: number; strokeWidth?: number }>
  onSelect: () => void
}

export default function ToolListItem({ title, description, icon: Icon, onSelect }: ToolListItemProps) {
  return (
    <button type="button" onClick={onSelect}>
      <Icon size={25} strokeWidth={1.75} />
      <span><strong>{title}</strong><small>{description}</small></span>
    </button>
  )
}
