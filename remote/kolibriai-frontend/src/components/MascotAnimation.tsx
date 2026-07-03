import { cn } from '@/lib/utils'

export type MascotState = 'idle' | 'ready' | 'thinking' | 'success' | 'alert' | 'error' | 'warning' | 'writing' | 'learning' | 'sleeping'

const MASCOT_ASSET = `${import.meta.env.BASE_URL}kolibri-bird.png`

const fallbackMotion: Record<Exclude<MascotState, 'warning' | 'writing' | 'learning'>, string> = {
  idle: 'kolibri-mascot-idle',
  ready: 'kolibri-mascot-ready',
  thinking: 'kolibri-mascot-thinking',
  success: 'kolibri-mascot-success',
  alert: 'kolibri-mascot-alert',
  error: 'kolibri-mascot-alert',
  sleeping: 'kolibri-mascot-sleeping',
}

function normalizeState(state: MascotState): Exclude<MascotState, 'warning' | 'writing' | 'learning'> {
  if (state === 'warning') return 'alert'
  if (state === 'writing') return 'thinking'
  if (state === 'learning') return 'ready'
  return state
}

interface MascotAnimationProps {
  state?: MascotState
  className?: string
  alt?: string
  decorative?: boolean
}

export default function MascotAnimation({
  state = 'idle',
  className,
  alt = 'Колибри',
  decorative = false,
}: MascotAnimationProps) {
  const normalized = normalizeState(state)

  return (
    <span
      className={cn(
        'kolibri-mascot relative inline-flex shrink-0 items-center justify-center overflow-visible align-middle',
        fallbackMotion[normalized],
        className,
      )}
      data-mascot-asset={MASCOT_ASSET}
      data-mascot-state={normalized}
      role={decorative ? undefined : 'img'}
      aria-label={decorative ? undefined : alt}
      aria-hidden={decorative ? true : undefined}
    >
      <img
        src={MASCOT_ASSET}
        alt=""
        className="h-full w-full object-contain [image-rendering:auto]"
        draggable={false}
      />
    </span>
  )
}
