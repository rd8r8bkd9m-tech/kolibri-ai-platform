import { cn } from '@/lib/utils'

export type MascotState =
  | 'idle'
  | 'thinking'
  | 'ready'
  | 'success'
  | 'warning'
  | 'error'
  | 'writing'
  | 'learning'
  | 'sleeping'

interface CartoonMascotProps {
  state?: MascotState
  size?: number
  className?: string
}

/**
 * The official production asset is the only Kolibri bird. State is expressed
 * with motion around the unchanged PNG, never with a substitute illustration.
 */
export default function CartoonMascot({
  state = 'idle',
  size = 48,
  className,
}: CartoonMascotProps) {
  return (
    <img
      src="/kolibri-bird.png"
      alt="Колибри"
      width={size}
      height={size}
      draggable={false}
      className={cn('kolibri-mascot', `kolibri-mascot-${state}`, className)}
      style={{ width: size, height: size, objectFit: 'contain' }}
    />
  )
}
