import { Equal, X } from 'lucide-react'

interface MobileNavigationTriggerProps {
  open: boolean
  conversationSurface: boolean
  conversationHasContent: boolean
  openLabel: string
  closeLabel: string
  onToggle: () => void
}

export default function MobileNavigationTrigger({
  open,
  openLabel,
  closeLabel,
  onToggle,
}: MobileNavigationTriggerProps) {
  return (
    <button
      type="button"
      onClick={onToggle}
      className="shell-mobile-morph"
      aria-label={open ? closeLabel : openLabel}
      aria-expanded={open}
    >
      {open ? <X size={22} strokeWidth={1.8} /> : <Equal size={23} strokeWidth={1.8} />}
    </button>
  )
}
