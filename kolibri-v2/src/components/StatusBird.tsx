import { cn } from '@/lib/utils'
import CartoonMascot, { type MascotState } from './CartoonMascot'

export type BirdState = MascotState

interface StatusBirdProps {
  state: BirdState
  size?: 'sm' | 'md' | 'lg'
  showLabel?: boolean
  className?: string
}

const stateConfig: Record<BirdState, { color: string; ring: string; label: string }> = {
  idle:     { color: 'text-[var(--text-tertiary)]',     ring: 'ring-[var(--border-subtle)]', label: 'Ожидание' },
  thinking: { color: 'text-[var(--accent-teal)]',       ring: 'ring-[var(--accent-teal)]/30', label: 'Думаю...' },
  ready:    { color: 'text-[var(--accent-teal)]',       ring: 'ring-[var(--accent-teal)]/20', label: 'Готов' },
  success:  { color: 'text-emerald-500',                ring: 'ring-emerald-500/20',          label: 'Готово' },
  warning:  { color: 'text-amber-500',                  ring: 'ring-amber-500/20',            label: 'Внимание' },
  error:    { color: 'text-red-500',                     ring: 'ring-red-500/20',              label: 'Ошибка' },
  writing:  { color: 'text-[var(--accent-lavender)]',   ring: 'ring-[var(--accent-lavender)]/20', label: 'Пишу...' },
  learning: { color: 'text-[var(--status-info)]',       ring: 'ring-[var(--status-info)]/20', label: 'Учусь...' },
  sleeping: { color: 'text-gray-400',                   ring: 'ring-gray-300/20',             label: 'Сплю' },
}

const sizeMap = { sm: 'w-8 h-8', md: 'w-12 h-12', lg: 'w-20 h-20' }
const mascotSize = { sm: 28, md: 40, lg: 64 }

export default function StatusBird({ state, size = 'md', showLabel = false, className }: StatusBirdProps) {
  const cfg = stateConfig[state]

  return (
    <div className={cn('flex flex-col items-center gap-1', className)}>
      <div
        className={cn(
          'relative flex items-center justify-center rounded-full ring-2 transition-all duration-300',
          sizeMap[size],
          cfg.ring,
        )}
      >
        <CartoonMascot
          state={state}
          size={mascotSize[size]}
          className={cn('transition-all duration-300', cfg.color)}
        />
        {state === 'thinking' && (
          <div className="absolute -top-0.5 -right-0.5 w-2.5 h-2.5 bg-[var(--accent-teal)] rounded-full animate-ping" />
        )}
        {state === 'success' && (
          <div className="absolute -top-0.5 -right-0.5 w-2.5 h-2.5 bg-emerald-500 rounded-full" />
        )}
        {state === 'error' && (
          <div className="absolute -top-0.5 -right-0.5 w-2.5 h-2.5 bg-red-500 rounded-full" />
        )}
      </div>
      {showLabel && (
        <span className={cn('text-[11px] font-medium', cfg.color)}>{cfg.label}</span>
      )}
    </div>
  )
}
