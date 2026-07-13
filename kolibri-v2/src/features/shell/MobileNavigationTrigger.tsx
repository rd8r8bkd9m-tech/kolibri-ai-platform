import { Menu, X } from 'lucide-react'
import CartoonMascot from '@/components/CartoonMascot'

interface MobileNavigationTriggerProps {
  open: boolean
  conversationSurface: boolean
  conversationHasContent: boolean
  openLabel: string
  closeLabel: string
  onToggle: () => void
}

/**
 * Owns the only header slot which can morph between the Kolibri character and
 * menu chrome. Empty conversations keep the bird in the canvas; populated
 * conversations move it into this slot, so one screen never renders two birds.
 */
export default function MobileNavigationTrigger({
  open,
  conversationSurface,
  conversationHasContent,
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
      {open ? <X size={24} /> : conversationSurface && !conversationHasContent ? (
        <Menu size={28} strokeWidth={1.8} />
      ) : (
        <>
          <CartoonMascot size={42} className="mobile-morph-bird" />
          <Menu size={24} className="mobile-morph-menu" />
        </>
      )}
    </button>
  )
}
