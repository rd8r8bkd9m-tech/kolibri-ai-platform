import { cn } from '@/lib/utils'
import MascotAnimation from './MascotAnimation'

export type BirdState = 'idle' | 'thinking' | 'ready' | 'success' | 'warning' | 'error' | 'writing' | 'learning' | 'sleeping'

const stateConfig: Record<BirdState, { color: string; ring: string; animation: string; label: string }> = {
  idle:     { color: 'text-[var(--text-tertiary)]',     ring: 'ring-[var(--border-subtle)]', animation: '',                    label: 'Ожидание' },
  thinking: { color: 'text-[var(--accent-teal)]',       ring: 'ring-[var(--accent-teal)]/30', animation: 'animate-spin-slow',  label: 'Думаю...' },
  ready:    { color: 'text-[var(--accent-teal)]',       ring: 'ring-[var(--accent-teal)]/20', animation: 'animate-pulse',      label: 'Готов' },
  success:  { color: 'text-emerald-500',                ring: 'ring-emerald-500/20',          animation: 'animate-bounce-once',label: 'Готово' },
  warning:  { color: 'text-amber-500',                  ring: 'ring-amber-500/20',            animation: 'animate-shake',      label: 'Внимание' },
  error:    { color: 'text-red-500',                     ring: 'ring-red-500/20',              animation: 'animate-shake',      label: 'Ошибка' },
  writing:  { color: 'text-[var(--accent-lavender)]',   ring: 'ring-[var(--accent-lavender)]/20', animation: 'animate-pulse',  label: 'Пишу...' },
  learning: { color: 'text-[var(--status-info)]',       ring: 'ring-[var(--status-info)]/20', animation: 'animate-pulse',       label: 'Учусь...' },
  sleeping: { color: 'text-gray-400',                   ring: 'ring-gray-300/20',             animation: '',                    label: 'Сплю' },
}

interface StatusBirdProps {
  state: BirdState
  size?: 'sm' | 'md' | 'lg' | 'xl'
  showLabel?: boolean
  className?: string
}

export default function StatusBird({ state, size = 'md', showLabel = false, className }: StatusBirdProps) {
  const cfg = stateConfig[state]
  const sizeMap = { sm: 'w-8 h-8', md: 'w-12 h-12', lg: 'w-20 h-20', xl: 'w-28 h-28' }
  const imgSize = { sm: 'w-8 h-8', md: 'w-12 h-12', lg: 'w-20 h-20', xl: 'w-28 h-28' }

  return (
    <div className={cn('flex flex-col items-center gap-1', className)}>
      <div
        className={cn(
          'relative flex items-center justify-center rounded-full ring-2 transition-all duration-300',
          sizeMap[size],
          cfg.ring,
          cfg.animation,
        )}
      >
        <MascotAnimation state={state} className={imgSize[size]} alt="Колибри" />
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
