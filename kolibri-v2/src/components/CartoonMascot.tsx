import { useState } from 'react'
import { cn } from '@/lib/utils'
import AnimatedMascot, { type MascotState } from './AnimatedMascot'

export type { MascotState }

interface CartoonMascotProps {
  state?: MascotState
  size?: number
  className?: string
}

const STATE_TO_APNG: Record<MascotState, string> = {
  idle: '/mascot/kolibri-idle.png',
  thinking: '/mascot/kolibri-thinking.png',
  ready: '/mascot/kolibri-ready.png',
  success: '/mascot/kolibri-success.png',
  warning: '/mascot/kolibri-alert.png',
  error: '/mascot/kolibri-alert.png',
  writing: '/mascot/kolibri-thinking.png',
  learning: '/mascot/kolibri-ready.png',
  sleeping: '/mascot/kolibri-sleeping.png',
}

export default function CartoonMascot({
  state = 'idle',
  size = 48,
  className,
}: CartoonMascotProps) {
  const [imgError, setImgError] = useState(false)
  const src = STATE_TO_APNG[state]

  if (imgError) {
    return <AnimatedMascot state={state} size={size} className={className} />
  }

  return (
    <div
      className={cn('am-mascot', className)}
      style={{ width: size, height: size }}
    >
      <img
        src={src}
        alt="Колибри"
        width={size}
        height={size}
        style={{ width: '100%', height: '100%', objectFit: 'contain' }}
        onError={() => setImgError(true)}
      />
    </div>
  )
}
