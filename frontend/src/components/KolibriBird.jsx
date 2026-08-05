import { motion } from "framer-motion";

const stateLabels = {
  idle: "спокойна",
  greeting: "приветствует",
  listening: "слушает",
  thinking: "думает",
  writing: "пишет",
  learning: "учится",
  success: "готово",
  error: "нужна помощь",
  calm: "спокойна",
  flying: "летит",
};

/**
 * The official kolibriai.ru mascot is the only brand artwork allowed in the
 * product. Keep animation on the wrapper so the source PNG stays unchanged.
 */
export function KolibriBird({ state = "idle", size = 56, className = "" }) {
  const px = typeof size === "number" ? size : 56;
  const animate = state === "thinking" || state === "learning"
    ? { y: [0, -2, 0], rotate: [-1, 1, -1] }
    : state === "flying"
      ? { x: [0, 3, 0], y: [0, -4, 0], rotate: [-2, 3, -2] }
      : state === "success"
        ? { scale: [1, 1.035, 1] }
        : {};

  return (
    <motion.img
      alt={`Маскот Kolibri: ${stateLabels[state] || state}`}
      animate={animate}
      className={`kolibri-mascot kolibri-mascot--${state} ${className}`}
      draggable="false"
      height={px}
      src="/kolibri-bird.png"
      transition={{ duration: 1.8, repeat: Object.keys(animate).length ? Infinity : 0 }}
      width={px}
    />
  );
}
