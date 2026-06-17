import { motion } from "framer-motion"

const states = {
  idle: { y: [0, -6, 0], duration: 3 },
  thinking: { y: [0, -3, 0], duration: 1.5 },
  happy: { y: [0, -12, 0], duration: 0.8 },
  error: { y: [0, 2, 0], duration: 2 },
}

export function KolibriBird({ size = 72, className = "", state = "idle" }) {
  const anim = states[state] || states.idle
  return (
    <motion.svg
      width={size}
      height={size}
      viewBox="0 0 120 120"
      fill="none"
      className={className}
      animate={{ y: anim.y }}
      transition={{ duration: anim.duration, repeat: Infinity, ease: "easeInOut" }}
    >
      <defs>
        <linearGradient id="birdGrad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#79E8FF" />
          <stop offset="50%" stopColor="#26BDF2" />
          <stop offset="100%" stopColor="#0B8FF3" />
        </linearGradient>
        <linearGradient id="wingGrad" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stopColor="#26BDF2" />
          <stop offset="100%" stopColor="#0B8FF3" stopOpacity="0.6" />
        </linearGradient>
        <filter id="birdGlow">
          <feGaussianBlur stdDeviation="3" result="blur" />
          <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
        </filter>
      </defs>
      
      <motion.circle
        cx="60" cy="55" r="40"
        fill="url(#birdGrad)"
        opacity="0.12"
        animate={{ r: [38, 42, 38], opacity: [0.1, 0.18, 0.1] }}
        transition={{ duration: 2, repeat: Infinity }}
      />
      
      <motion.ellipse
        cx="60" cy="55" rx="22" ry="26"
        fill="url(#birdGrad)"
        filter="url(#birdGlow)"
        animate={{ ry: [26, 27, 26] }}
        transition={{ duration: 2, repeat: Infinity }}
      />
      
      <circle cx="60" cy="32" r="14" fill="url(#birdGrad)" />
      
      <circle cx="55" cy="30" r="3.5" fill="white" />
      <motion.circle
        cx="55" cy="30" r="2"
        fill="#0a1628"
        animate={state === "thinking" 
          ? { cx: [55, 52, 55, 58, 55], cy: [30, 29, 30, 29, 30] }
          : { cx: [55, 54, 55, 56, 55] }
        }
        transition={{ duration: state === "thinking" ? 1.5 : 4, repeat: Infinity }}
      />
      
      {state === "happy" && (
        <>
          <motion.path d="M50 34 Q55 38 60 34" stroke="#0a1628" strokeWidth="1.5" fill="none"
            initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} />
        </>
      )}
      
      <path d="M42 33 L30 36 L42 38 Z" fill="#F59E0B" />
      
      <motion.path
        d="M75 45 Q95 35 90 55 Q85 65 75 60 Z"
        fill="url(#wingGrad)"
        animate={{
          d: state === "happy"
            ? ["M75 45 Q100 20 95 50 Q88 62 75 60 Z", "M75 45 Q95 35 90 55 Q85 65 75 60 Z"]
            : ["M75 45 Q95 35 90 55 Q85 65 75 60 Z", "M75 45 Q100 25 95 50 Q88 62 75 60 Z", "M75 45 Q95 35 90 55 Q85 65 75 60 Z"],
        }}
        transition={{ duration: state === "happy" ? 0.6 : 1.5, repeat: Infinity, ease: "easeInOut" }}
      />
      
      <path d="M55 78 Q40 95 30 90 Q45 85 55 78" fill="#26BDF2" opacity="0.7" />
      
      <line x1="55" y1="80" x2="50" y2="95" stroke="#0B8FF3" strokeWidth="2" strokeLinecap="round" />
      <line x1="65" y1="80" x2="70" y2="95" stroke="#0B8FF3" strokeWidth="2" strokeLinecap="round" />
    </motion.svg>
  )
}
