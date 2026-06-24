const MEMORY_KEY = "kolibri-v3-memory"

export const DEFAULT_PROFILE = {
  id: "local-profile",
  name: "Локальный профиль",
  preferences: {},
  traces: [],
}

export function loadProfile() {
  try {
    const raw = localStorage.getItem(MEMORY_KEY)
    if (!raw) return DEFAULT_PROFILE
    const parsed = JSON.parse(raw)
    return { ...DEFAULT_PROFILE, ...parsed, traces: Array.isArray(parsed.traces) ? parsed.traces : [] }
  } catch {
    return DEFAULT_PROFILE
  }
}

export function saveProfile(profile) {
  localStorage.setItem(MEMORY_KEY, JSON.stringify(profile))
  return profile
}

export function addTrace(profile, trace) {
  const next = {
    ...profile,
    traces: [
      {
        id: `trace_${Date.now().toString(36)}`,
        createdAt: new Date().toISOString(),
        source: trace.source || "chat",
        context: trace.context || "",
        action: trace.action || "",
        result: trace.result || "",
        tags: trace.tags || [],
        associations: trace.associations || [],
        confidence: Number(trace.confidence ?? 0.7),
        intuition: Number(trace.intuition ?? 0.5),
        emotion: trace.emotion || "focused",
        colorMark: trace.colorMark || "green",
        privacy: trace.privacy || "local",
        canvasId: trace.canvasId,
      },
      ...profile.traces,
    ].slice(0, 40),
  }
  return saveProfile(next)
}

export function resetProfile() {
  localStorage.removeItem(MEMORY_KEY)
  return DEFAULT_PROFILE
}
