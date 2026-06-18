import { motion } from "framer-motion"
import mascotImg from "../assets/kolibri-mascot.png"

const stateLabels = {
  idle: "спокойна",
  greeting: "приветствует",
  listening: "слушает",
  thinking: "думает",
  writing: "пишет",
  learning: "учится",
  success: "готово",
  error: "нужна помощь",
  happy: "радуется",
  surprised: "удивлена",
  "angry-soft": "сердится мягко",
  calm: "спокойна",
  sleepy: "спит",
  flying: "летит",
}

export function KolibriBird({ state = "idle", size = 56, className = "" }) {
  const px = typeof size === "number" ? size : 56

  const animate =
    state === "thinking" || state === "learning"
      ? { y: [0, -4, 0], rotate: [-2, 2, -2] }
      : state === "flying"
        ? { x: [0, 5, 0], y: [0, -6, 0], rotate: [-5, 5, -5] }
        : state === "success" || state === "happy"
          ? { scale: [1, 1.08, 1] }
          : state === "error"
            ? { rotate: [0, -3, 3, 0] }
            : {}

  return (
    <motion.div
      className={`kolibri-mascot kolibri-mascot--${state} ${className}`}
      style={{
        width: px,
        height: px,
        borderRadius: "50%",
        overflow: "hidden",
        flexShrink: 0,
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
      }}
      animate={animate}
      transition={{
        duration: state === "error" ? 0.4 : 1.8,
        repeat: state === "idle" || state === "calm" ? 0 : Infinity,
        ease: "easeInOut",
      }}
      aria-label={`Колибри ${stateLabels[state] || state}`}
      role="img"
    >
      <img
        src={mascotImg}
        alt="Колибри"
        draggable={false}
        style={{
          width: "100%",
          height: "100%",
          objectFit: "cover",
          display: "block",
          userSelect: "none",
        }}
      />
    </motion.div>
  )
}
