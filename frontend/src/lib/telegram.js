export function getTelegramWebApp() {
  if (typeof window === "undefined") {
    return null
  }
  return window.Telegram?.WebApp ?? null
}

export function isTelegramMiniAppContext() {
  const webApp = getTelegramWebApp()
  if (!webApp || typeof window === "undefined") {
    return false
  }
  const locationHint = `${window.location.search}${window.location.hash}`
  return Boolean(
    webApp.initData ||
    webApp.initDataUnsafe?.user ||
    /tgWebApp/i.test(locationHint),
  )
}

function setCssVariable(name, value) {
  const root = document.documentElement
  if (value) {
    root.style.setProperty(name, value)
  } else {
    root.style.removeProperty(name)
  }
}

export function syncTelegramViewport(webApp) {
  if (!webApp || typeof document === "undefined") {
    return
  }
  const viewportHeight = Number(webApp.viewportHeight)
  const stableHeight = Number(webApp.viewportStableHeight || viewportHeight)
  if (viewportHeight > 0) {
    setCssVariable("--tg-viewport-height", `${viewportHeight}px`)
    setCssVariable("--app-height", `${viewportHeight}px`)
  }
  if (stableHeight > 0) {
    setCssVariable("--tg-viewport-stable-height", `${stableHeight}px`)
  }
}

export function applyTelegramTheme(webApp, fallbackTheme = "dark") {
  if (!webApp || typeof document === "undefined") {
    return fallbackTheme
  }

  const themeParams = webApp.themeParams || {}
  const colorVars = {
    bg_color: "--tg-bg-color",
    secondary_bg_color: "--tg-secondary-bg-color",
    section_bg_color: "--tg-section-bg-color",
    text_color: "--tg-text-color",
    hint_color: "--tg-hint-color",
    link_color: "--tg-link-color",
    button_color: "--tg-button-color",
    button_text_color: "--tg-button-text-color",
    accent_text_color: "--tg-accent-text-color",
  }

  Object.entries(colorVars).forEach(([source, target]) => {
    setCssVariable(target, themeParams[source] || "")
  })

  const nextTheme = webApp.colorScheme === "light" ? "light" : "dark"
  document.documentElement.dataset.tgColorScheme = nextTheme
  return nextTheme || fallbackTheme
}

export function bootstrapTelegramWebApp(onThemeChange) {
  const webApp = getTelegramWebApp()
  if (!webApp) {
    return () => {}
  }

  const sync = () => {
    const nextTheme = applyTelegramTheme(webApp)
    syncTelegramViewport(webApp)
    if (typeof onThemeChange === "function") {
      onThemeChange(nextTheme)
    }
    try {
      webApp.setHeaderColor?.("secondary_bg_color")
    } catch {}
    try {
      webApp.setBackgroundColor?.(webApp.themeParams?.bg_color || "")
    } catch {}
    try {
      webApp.setBottomBarColor?.(webApp.themeParams?.secondary_bg_color || webApp.themeParams?.bg_color || "")
    } catch {}
  }

  try {
    webApp.ready?.()
    webApp.expand?.()
    webApp.disableVerticalSwipes?.()
  } catch {}

  sync()
  webApp.onEvent?.("themeChanged", sync)
  webApp.onEvent?.("viewportChanged", sync)

  return () => {
    webApp.offEvent?.("themeChanged", sync)
    webApp.offEvent?.("viewportChanged", sync)
  }
}
