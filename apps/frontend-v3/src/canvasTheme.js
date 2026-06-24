const THEME_PRESETS = {
  dawn: {
    name: "dawn",
    mode: "light",
    backgroundStops: ["#fff7ed", "#f8fbff", "#d9f4ff", "#9fe4ff"],
    accent: "#20b7c8",
    accentSoft: "rgba(32, 183, 200, 0.18)",
    text: "#102a33",
    textMuted: "rgba(16, 42, 51, 0.68)",
    panelFill: "rgba(255, 255, 255, 0.68)",
    panelStroke: "rgba(32, 183, 200, 0.22)",
    auroraA: "rgba(255, 214, 165, 0.28)",
    auroraB: "rgba(53, 227, 229, 0.16)",
    auroraC: "rgba(255, 255, 255, 0.2)",
    grid: "rgba(25, 94, 115, 0.04)",
    horizonA: "rgba(255,255,255,0.36)",
    horizonB: "rgba(214,246,255,0.22)",
    horizonC: "rgba(84,183,218,0.2)",
  },
  day: {
    name: "day",
    mode: "light",
    backgroundStops: ["#fbfdff", "#f7fbff", "#d7f3ff", "#93dcff"],
    accent: "#18b8c8",
    accentSoft: "rgba(24, 184, 200, 0.18)",
    text: "#0d2b34",
    textMuted: "rgba(13, 43, 52, 0.66)",
    panelFill: "rgba(255, 255, 255, 0.7)",
    panelStroke: "rgba(24, 184, 200, 0.22)",
    auroraA: "rgba(53, 227, 229, 0.22)",
    auroraB: "rgba(91, 161, 255, 0.13)",
    auroraC: "rgba(255, 255, 255, 0.18)",
    grid: "rgba(25, 94, 115, 0.045)",
    horizonA: "rgba(255,255,255,0.26)",
    horizonB: "rgba(214,246,255,0.2)",
    horizonC: "rgba(84,183,218,0.22)",
  },
  dusk: {
    name: "dusk",
    mode: "light",
    backgroundStops: ["#fff9f2", "#f5f8ff", "#d6eefc", "#b5d6ff"],
    accent: "#7c8cff",
    accentSoft: "rgba(124, 140, 255, 0.16)",
    text: "#19243c",
    textMuted: "rgba(25, 36, 60, 0.66)",
    panelFill: "rgba(255, 255, 255, 0.66)",
    panelStroke: "rgba(124, 140, 255, 0.2)",
    auroraA: "rgba(251, 191, 36, 0.16)",
    auroraB: "rgba(124, 140, 255, 0.16)",
    auroraC: "rgba(53, 227, 229, 0.12)",
    grid: "rgba(64, 74, 126, 0.04)",
    horizonA: "rgba(255,255,255,0.26)",
    horizonB: "rgba(222,232,255,0.22)",
    horizonC: "rgba(129,160,230,0.2)",
  },
  night: {
    name: "night",
    mode: "dark",
    backgroundStops: ["#0b1f2b", "#0e2f3a", "#10273f", "#1b2b3f"],
    accent: "#35e3e5",
    accentSoft: "rgba(53, 227, 229, 0.16)",
    text: "#eef9fb",
    textMuted: "rgba(238,249,251,0.68)",
    panelFill: "rgba(6, 16, 19, 0.62)",
    panelStroke: "rgba(53, 227, 229, 0.24)",
    auroraA: "rgba(53, 227, 229, 0.22)",
    auroraB: "rgba(70, 243, 192, 0.12)",
    auroraC: "rgba(124, 140, 255, 0.1)",
    grid: "rgba(214, 255, 250, 0.052)",
    horizonA: "rgba(255,255,255,0.06)",
    horizonB: "rgba(6,16,19,0.08)",
    horizonC: "rgba(0,0,0,0.2)",
  },
}

export function resolveCanvasTheme({ now = new Date(), text = "", manifestTheme = null } = {}) {
  const requested = requestedThemeFromText(text)
  const baseName = safeThemeName(manifestTheme?.name || manifestTheme?.preset || requested || timeThemeName(now))
  const preset = THEME_PRESETS[baseName] || THEME_PRESETS.day
  return normalizeTheme({
    ...preset,
    ...safeManifestTheme(manifestTheme),
    name: baseName,
  })
}

export function mixCanvasTheme(previousTheme, nextTheme, progress = 1) {
  if (!previousTheme) return nextTheme
  const amount = Math.max(0, Math.min(1, Number(progress)))
  return {
    ...nextTheme,
    backgroundStops: mixColorList(previousTheme.backgroundStops, nextTheme.backgroundStops, amount),
    accent: mixColor(previousTheme.accent, nextTheme.accent, amount),
    accentSoft: mixColor(previousTheme.accentSoft, nextTheme.accentSoft, amount),
    text: mixColor(previousTheme.text, nextTheme.text, amount),
    textMuted: mixColor(previousTheme.textMuted, nextTheme.textMuted, amount),
    panelFill: mixColor(previousTheme.panelFill, nextTheme.panelFill, amount),
    panelStroke: mixColor(previousTheme.panelStroke, nextTheme.panelStroke, amount),
    auroraA: mixColor(previousTheme.auroraA, nextTheme.auroraA, amount),
    auroraB: mixColor(previousTheme.auroraB, nextTheme.auroraB, amount),
    auroraC: mixColor(previousTheme.auroraC, nextTheme.auroraC, amount),
    grid: mixColor(previousTheme.grid, nextTheme.grid, amount),
    horizonA: mixColor(previousTheme.horizonA, nextTheme.horizonA, amount),
    horizonB: mixColor(previousTheme.horizonB, nextTheme.horizonB, amount),
    horizonC: mixColor(previousTheme.horizonC, nextTheme.horizonC, amount),
  }
}

function requestedThemeFromText(text) {
  const value = String(text || "").toLowerCase()
  if (/(night|dark|темн|ночн|ночь)/i.test(value)) return "night"
  if (/(morning|sunrise|утро|утрен)/i.test(value)) return "dawn"
  if (/(evening|sunset|вечер|закат)/i.test(value)) return "dusk"
  if (/(light|clean|светл|легк|чист)/i.test(value)) return "day"
  return ""
}

function timeThemeName(now) {
  const hour = new Date(now).getHours()
  if (hour >= 5 && hour < 10) return "dawn"
  if (hour >= 10 && hour < 18) return "day"
  if (hour >= 18 && hour < 22) return "dusk"
  return "night"
}

function safeThemeName(value) {
  const name = String(value || "").toLowerCase()
  return Object.hasOwn(THEME_PRESETS, name) ? name : "day"
}

function safeManifestTheme(theme) {
  if (!theme || typeof theme !== "object") return {}
  const result = {}
  for (const key of ["accent", "accentSoft", "text", "textMuted", "panelFill", "panelStroke", "auroraA", "auroraB", "auroraC", "grid", "horizonA", "horizonB", "horizonC"]) {
    if (isSafeColor(theme[key])) result[key] = theme[key]
  }
  if (Array.isArray(theme.backgroundStops)) {
    const stops = theme.backgroundStops.filter(isSafeColor).slice(0, 6)
    if (stops.length >= 2) result.backgroundStops = stops
  }
  if (theme.mode === "light" || theme.mode === "dark") result.mode = theme.mode
  return result
}

function normalizeTheme(theme) {
  return {
    ...THEME_PRESETS.day,
    ...theme,
    backgroundStops: Array.isArray(theme.backgroundStops) && theme.backgroundStops.length >= 2
      ? theme.backgroundStops
      : THEME_PRESETS.day.backgroundStops,
  }
}

function isSafeColor(value) {
  return typeof value === "string" && /^(#[0-9a-f]{3,8}|rgba?\([0-9.,%\s]+\))$/i.test(value.trim())
}

function mixColorList(previousStops = [], nextStops = [], amount) {
  const length = Math.max(previousStops.length, nextStops.length, 2)
  return Array.from({ length }, (_, index) => mixColor(
    previousStops[index] || previousStops[previousStops.length - 1] || nextStops[index],
    nextStops[index] || nextStops[nextStops.length - 1] || previousStops[index],
    amount,
  ))
}

function mixColor(previousColor, nextColor, amount) {
  const from = parseColor(previousColor)
  const to = parseColor(nextColor)
  if (!from || !to) return amount < 1 ? previousColor : nextColor
  const mixed = from.map((channel, index) => channel + (to[index] - channel) * amount)
  return `rgba(${Math.round(mixed[0])}, ${Math.round(mixed[1])}, ${Math.round(mixed[2])}, ${roundAlpha(mixed[3])})`
}

function parseColor(value) {
  const color = String(value || "").trim()
  const hex = color.match(/^#([0-9a-f]{3}|[0-9a-f]{6}|[0-9a-f]{8})$/i)
  if (hex) {
    const raw = hex[1]
    const full = raw.length === 3 ? raw.split("").map(char => char + char).join("") : raw
    return [
      Number.parseInt(full.slice(0, 2), 16),
      Number.parseInt(full.slice(2, 4), 16),
      Number.parseInt(full.slice(4, 6), 16),
      full.length === 8 ? Number.parseInt(full.slice(6, 8), 16) / 255 : 1,
    ]
  }
  const rgb = color.match(/^rgba?\(([^)]+)\)$/i)
  if (!rgb) return null
  const parts = rgb[1].split(",").map(part => Number.parseFloat(part.trim()))
  if (parts.length < 3 || parts.some((part, index) => index < 3 && !Number.isFinite(part))) return null
  return [parts[0], parts[1], parts[2], Number.isFinite(parts[3]) ? parts[3] : 1]
}

function roundAlpha(value) {
  return Math.max(0, Math.min(1, Number(value))).toFixed(3).replace(/0+$/, "").replace(/\.$/, "")
}
