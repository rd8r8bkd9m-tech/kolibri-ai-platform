import { useMemo } from 'react'
import { cn } from '@/lib/utils'

export type MascotState = 'idle' | 'thinking' | 'ready' | 'success' | 'warning' | 'error' | 'writing' | 'learning' | 'sleeping'

interface AnimatedMascotProps {
  state?: MascotState
  size?: number
  className?: string
}

const stateAnimations: Record<MascotState, {
  body: string
  wingL: string
  wingR: string
  eyeLid: string
  pupil: string
  beak: string
}> = {
  idle: {
    body: 'am-body-breathe 4s ease-in-out infinite',
    wingL: 'am-wing-idle 3.5s ease-in-out infinite',
    wingR: 'am-wing-idle 3.5s ease-in-out infinite 0.15s',
    eyeLid: 'am-blink 5s ease-in-out infinite',
    pupil: '',
    beak: '',
  },
  thinking: {
    body: 'am-body-think 1.8s ease-in-out infinite',
    wingL: 'am-wing-think 0.6s ease-in-out infinite',
    wingR: 'am-wing-think 0.6s ease-in-out infinite 0.08s',
    eyeLid: 'am-blink 3s ease-in-out infinite',
    pupil: 'am-pupil-think 2.5s ease-in-out infinite',
    beak: '',
  },
  ready: {
    body: 'am-body-breathe 3.2s ease-in-out infinite',
    wingL: 'am-wing-ready 2.8s ease-in-out infinite',
    wingR: 'am-wing-ready 2.8s ease-in-out infinite 0.1s',
    eyeLid: 'am-blink 4s ease-in-out infinite',
    pupil: '',
    beak: '',
  },
  success: {
    body: 'am-body-jump 0.7s cubic-bezier(0.34,1.56,0.64,1)',
    wingL: 'am-wing-happy 0.5s ease-in-out 3',
    wingR: 'am-wing-happy 0.5s ease-in-out 3 0.06s',
    eyeLid: '',
    pupil: '',
    beak: 'am-beak-happy 0.7s ease-out',
  },
  warning: {
    body: 'am-body-alert 1s ease-in-out 2',
    wingL: 'am-wing-alert 0.5s ease-in-out 2',
    wingR: 'am-wing-alert 0.5s ease-in-out 2 0.1s',
    eyeLid: 'am-blink 2s ease-in-out infinite',
    pupil: 'am-pupil-alert 1s ease-in-out infinite',
    beak: '',
  },
  error: {
    body: 'am-body-alert 0.8s ease-in-out 2',
    wingL: 'am-wing-alert 0.4s ease-in-out 3',
    wingR: 'am-wing-alert 0.4s ease-in-out 3 0.08s',
    eyeLid: 'am-blink-fast 1.5s ease-in-out infinite',
    pupil: 'am-pupil-alert 0.8s ease-in-out infinite',
    beak: '',
  },
  writing: {
    body: 'am-body-breathe 3s ease-in-out infinite',
    wingL: 'am-wing-think 0.8s ease-in-out infinite',
    wingR: 'am-wing-think 0.8s ease-in-out infinite 0.1s',
    eyeLid: 'am-blink 3.5s ease-in-out infinite',
    pupil: 'am-pupil-think 3s ease-in-out infinite',
    beak: '',
  },
  learning: {
    body: 'am-body-breathe 3.5s ease-in-out infinite',
    wingL: 'am-wing-ready 2.2s ease-in-out infinite',
    wingR: 'am-wing-ready 2.2s ease-in-out infinite 0.12s',
    eyeLid: 'am-blink 3s ease-in-out infinite',
    pupil: '',
    beak: '',
  },
  sleeping: {
    body: 'am-body-sleep 6s ease-in-out infinite',
    wingL: '',
    wingR: '',
    eyeLid: 'am-eye-sleep',
    pupil: '',
    beak: '',
  },
}

export default function AnimatedMascot({ state = 'idle', size = 48, className }: AnimatedMascotProps) {
  const anim = stateAnimations[state]
  const isSleeping = state === 'sleeping'
  const isAlert = state === 'warning' || state === 'error'
  const isSuccess = state === 'success'

  const style = useMemo(() => ({
    width: size,
    height: size,
  }), [size])

  return (
    <div className={cn('am-mascot', className)} style={style}>
      <svg
        viewBox="0 0 100 100"
        width={size}
        height={size}
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className="am-svg"
        role="img"
        aria-label="Колибри"
      >
        {/* Tail feathers */}
        <g className="am-tail" style={{ animation: anim.body, transformOrigin: '45px 62px' }}>
          <path d="M38 60 Q28 72 22 82 Q30 75 36 65Z" fill="#2BA8B4" opacity="0.7" />
          <path d="M40 62 Q32 76 26 86 Q33 78 39 67Z" fill="#3ABAB4" opacity="0.8" />
          <path d="M42 63 Q36 78 32 88 Q37 80 42 68Z" fill="#2BA8B4" opacity="0.65" />
        </g>

        {/* Left wing */}
        <g
          className="am-wing-l"
          style={{
            animation: anim.wingL,
            transformOrigin: '42px 48px',
          }}
        >
          <path
            d="M42 48 Q30 38 18 32 Q22 42 28 48 Q24 44 16 40 Q22 50 30 52 Q34 50 42 48Z"
            fill="#3ABAB4"
            opacity="0.85"
          />
          <path
            d="M42 48 Q34 42 22 36 Q26 44 32 49Z"
            fill="#2BA8B4"
            opacity="0.6"
          />
        </g>

        {/* Right wing */}
        <g
          className="am-wing-r"
          style={{
            animation: anim.wingR,
            transformOrigin: '58px 48px',
          }}
        >
          <path
            d="M58 48 Q70 38 82 32 Q78 42 72 48 Q76 44 84 40 Q78 50 70 52 Q66 50 58 48Z"
            fill="#3ABAB4"
            opacity="0.85"
          />
          <path
            d="M58 48 Q66 42 78 36 Q74 44 68 49Z"
            fill="#2BA8B4"
            opacity="0.6"
          />
        </g>

        {/* Body */}
        <g style={{ animation: anim.body, transformOrigin: '50px 55px' }}>
          {/* Body shadow */}
          <ellipse cx="50" cy="68" rx="14" ry="3" fill="#2BA8B4" opacity="0.15" />

          {/* Main body */}
          <ellipse cx="50" cy="55" rx="16" ry="18" fill="#3ABAB4" />

          {/* Belly highlight */}
          <ellipse cx="50" cy="58" rx="10" ry="11" fill="#5CC8C4" opacity="0.6" />

          {/* Belly lighter spot */}
          <ellipse cx="50" cy="60" rx="7" ry="8" fill="#7DD8D5" opacity="0.4" />
        </g>

        {/* Head */}
        <g style={{ animation: anim.body, transformOrigin: '50px 35px' }}>
          <circle cx="50" cy="35" r="12" fill="#3ABAB4" />

          {/* Head highlight */}
          <circle cx="48" cy="33" r="8" fill="#5CC8C4" opacity="0.4" />

          {/* Crown feathers */}
          <path d="M47 24 Q46 18 49 16 Q50 20 50 24Z" fill="#2BA8B4" />
          <path d="M50 23 Q50 17 53 15 Q53 19 52 23Z" fill="#3ABAB4" opacity="0.8" />
        </g>

        {/* Eye white */}
        <ellipse cx="55" cy="33" rx="4.5" ry="5" fill="white" />

        {/* Pupil */}
        <g style={{ animation: anim.pupil || 'none', transformOrigin: '56px 33px' }}>
          <circle cx="56" cy="33" r="2.8" fill="#1a1a2e" />
          <circle cx="57" cy="32" r="1" fill="white" opacity="0.8" />
        </g>

        {/* Eyelid */}
        <g style={{ animation: anim.eyeLid || 'none', transformOrigin: '55px 33px' }}>
          {isSleeping ? (
            <path d="M50.5 33 Q55 35 59.5 33" stroke="#2BA8B4" strokeWidth="1.5" strokeLinecap="round" fill="none" />
          ) : (
            <rect x="50" y="28" width="10" height="10" fill="#3ABAB4" rx="1" style={{ clipPath: 'inset(0 0 100% 0)' }} className="am-eyelid" />
          )}
        </g>

        {/* Beak */}
        <g style={{ animation: anim.beak || 'none', transformOrigin: '58px 37px' }}>
          <path
            d="M60 36 L74 38 L60 40 Z"
            fill={isSuccess ? '#F59E0B' : '#E8734A'}
          />
          <path
            d="M60 36 L74 38 L60 38 Z"
            fill={isSuccess ? '#D97706' : '#D4603A'}
            opacity="0.6"
          />
        </g>

        {/* Cheek blush */}
        <circle cx="44" cy="38" r="3" fill="#F9A8D4" opacity={isAlert ? '0.5' : '0.3'} />

        {/* Z's for sleeping */}
        {isSleeping && (
          <g className="am-zzz">
            <text x="62" y="26" fontSize="6" fill="#3ABAB4" fontWeight="bold" opacity="0.6">z</text>
            <text x="67" y="20" fontSize="5" fill="#3ABAB4" fontWeight="bold" opacity="0.4">z</text>
            <text x="71" y="15" fontSize="4" fill="#3ABAB4" fontWeight="bold" opacity="0.3">z</text>
          </g>
        )}

        {/* Sparkle for success */}
        {isSuccess && (
          <g className="am-sparkle">
            <text x="20" y="28" fontSize="7" fill="#F59E0B">★</text>
            <text x="74" y="24" fontSize="5" fill="#F59E0B" opacity="0.7">★</text>
            <text x="16" y="42" fontSize="4" fill="#F59E0B" opacity="0.5">★</text>
          </g>
        )}

        {/* Alert exclamation */}
        {isAlert && (
          <g className="am-alert-mark">
            <text x="72" y="22" fontSize="8" fill={state === 'error' ? '#EF4444' : '#F59E0B'} fontWeight="bold">!</text>
          </g>
        )}
      </svg>
    </div>
  )
}
