import { motion } from "framer-motion";

type AssistantState =
  | "idle" | "greeting" | "listening" | "thinking" | "writing"
  | "learning" | "success" | "error" | "happy" | "surprised"
  | "angry-soft" | "calm" | "sleepy" | "flying";

function cn(...inputs: (string | undefined | false)[]) {
  return inputs.filter(Boolean).join(" ");
}

const stateLabels: Record<AssistantState, string> = {
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
};

export function KolibriAvatar({
  state = "idle",
  size = "md",
  className,
}: {
  state?: AssistantState;
  size?: "sm" | "md" | "lg";
  className?: string;
}) {
  const px = size === "sm" ? 38 : size === "lg" ? 86 : 56;
  const animate =
    state === "thinking" || state === "learning"
      ? { y: [0, -3, 0], rotate: [-1, 1, -1] }
      : state === "flying"
        ? { x: [0, 4, 0], y: [0, -5, 0], rotate: [-4, 5, -4] }
        : state === "success" || state === "happy"
          ? { scale: [1, 1.06, 1] }
          : {};

  return (
    <motion.div
      className={cn("kolibri-avatar", `kolibri-avatar--${state}`, className)}
      style={{ width: px, height: px }}
      animate={animate}
      transition={{ duration: 1.8, repeat: state === "idle" || state === "calm" ? 0 : Infinity }}
      aria-label={`Калибри ${stateLabels[state]}`}
      role="img"
    >
      <svg viewBox="0 0 112 112" aria-hidden="true">
        <defs>
          <linearGradient id={`kolibriBody-${state}`} x1="32" x2="82" y1="18" y2="78" gradientUnits="userSpaceOnUse">
            <stop stopColor="#79E8FF" />
            <stop offset="0.48" stopColor="#26BDF2" />
            <stop offset="1" stopColor="#0B8FF3" />
          </linearGradient>
          <linearGradient id={`kolibriWing-${state}`} x1="12" x2="57" y1="20" y2="64" gradientUnits="userSpaceOnUse">
            <stop stopColor="#8CF5FF" />
            <stop offset="1" stopColor="#1096F4" />
          </linearGradient>
          <radialGradient id={`kolibriBelly-${state}`} cx="0" cy="0" r="1" gradientTransform="matrix(28 0 0 25 58 65)" gradientUnits="userSpaceOnUse">
            <stop stopColor="#FFFFFF" />
            <stop offset="1" stopColor="#E7FBFF" />
          </radialGradient>
        </defs>
        <ellipse className="kolibri-avatar__shadow" cx="57" cy="94" rx="25" ry="7" />
        <path className="kolibri-avatar__wing-back" fill={`url(#kolibriWing-${state})`} d="M30 58C16 53 8 40 12 27c17 3 31 15 41 33-7 7-15 8-23-2Z" />
        <path className="kolibri-avatar__tail" d="M36 70 17 86l24-1 9-12Z" />
        <path className="kolibri-avatar__body" fill={`url(#kolibriBody-${state})`} d="M35 67c-7-20 5-43 27-49 20-5 39 8 43 28 4 21-11 40-33 45-18 4-32-5-37-24Z" />
        <path className="kolibri-avatar__head-glow" d="M49 29c8-10 25-12 36-2 8 8 11 20 6 31-7-10-18-17-31-18-6 0-9-4-11-11Z" />
        <path className="kolibri-avatar__belly" fill={`url(#kolibriBelly-${state})`} d="M47 71c-5-13 2-29 17-33 14-3 25 5 29 17-3 16-14 28-31 31-7-1-12-6-15-15Z" />
        <path className="kolibri-avatar__wing" fill={`url(#kolibriWing-${state})`} d="M31 60C18 49 15 31 25 17c16 6 29 21 35 41-8 9-20 11-29 2Z" />
        <path className="kolibri-avatar__crest" d="M56 18c1-7 8-12 14-10-1 7-6 12-14 10Zm10 2c3-7 11-9 17-5-3 6-9 9-17 5Zm-19 5c-2-6 1-13 7-16 3 7 1 13-7 16Z" />
        <path className="kolibri-avatar__beak" d="M84 48 107 39 88 56Z" />
        <circle className="kolibri-avatar__cheek" cx="76" cy="60" r="7" />
        <circle className="kolibri-avatar__eye-white" cx="66" cy="43" r="11" />
        <circle className="kolibri-avatar__eye-white" cx="84" cy="43" r="9.5" />
        <circle className="kolibri-avatar__eye" cx="67" cy="44" r="6.5" />
        <circle className="kolibri-avatar__eye" cx="84" cy="44" r="5.8" />
        <circle className="kolibri-avatar__spark" cx="69.5" cy="41" r="2.2" />
        <circle className="kolibri-avatar__spark" cx="86" cy="41.5" r="1.8" />
        <path className="kolibri-avatar__smile" d="M73 54c3 3 7 3 10 0" />
        <path className="kolibri-avatar__foot" d="M57 88c-2 4-5 6-9 5" />
        <path className="kolibri-avatar__foot" d="M69 88c2 4 5 6 9 5" />
        {state === "surprised" ? <text className="kolibri-avatar__mark kolibri-avatar__mark--question" x="88" y="27">?</text> : null}
        {state === "error" ? <text className="kolibri-avatar__mark kolibri-avatar__mark--error" x="92" y="31">!</text> : null}
        {state === "sleepy" ? <text className="kolibri-avatar__mark kolibri-avatar__mark--sleep" x="86" y="27">Z</text> : null}
        {state === "learning" ? (
          <g className="kolibri-avatar__book">
            <path d="M65 70c8-5 16-5 23 0v15c-7-4-15-4-23 0Z" />
            <path d="M65 70c-8-5-16-5-23 0v15c7-4 15-4 23 0Z" />
            <path d="M65 70v15" />
          </g>
        ) : null}
        {state === "happy" || state === "success" ? (
          <g className="kolibri-avatar__sparkles">
            <path d="M96 61v10M91 66h10" />
            <path d="M28 24v7M24.5 27.5h7" />
          </g>
        ) : null}
        {state === "sleepy" ? (
          <>
            <path className="kolibri-avatar__lid" d="M58 43c5 3 11 3 16 0" />
            <path className="kolibri-avatar__lid" d="M79 43c4 2 9 2 13 0" />
          </>
        ) : null}
        {state === "angry-soft" ? (
          <>
            <path className="kolibri-avatar__brow" d="M58 35l14 4" />
            <path className="kolibri-avatar__brow" d="M90 35l-12 4" />
            <path className="kolibri-avatar__steam" d="M91 22c5 2 5 7 0 9" />
          </>
        ) : null}
      </svg>
      <span className="kolibri-avatar__glow" />
    </motion.div>
  );
}
