import { useEffect, useMemo, useState } from "react"

function readSystemTheme() {
  return window.matchMedia?.("(prefers-color-scheme: light)")?.matches ? "light" : "dark"
}

export function useThemeMode() {
  const [theme, setTheme] = useState(() => localStorage.getItem("kolibri-theme") || "system")
  const [systemTheme, setSystemTheme] = useState(readSystemTheme)
  const resolvedTheme = useMemo(() => theme === "system" ? systemTheme : theme, [theme, systemTheme])

  useEffect(() => {
    const media = window.matchMedia?.("(prefers-color-scheme: light)")
    if (!media) return undefined
    const updateTheme = () => setSystemTheme(media.matches ? "light" : "dark")
    updateTheme()
    media.addEventListener?.("change", updateTheme)
    return () => media.removeEventListener?.("change", updateTheme)
  }, [])

  useEffect(() => {
    const root = document.documentElement
    root.classList.remove("theme-dark", "theme-light")
    root.classList.add(resolvedTheme === "dark" ? "theme-dark" : "theme-light")
    localStorage.setItem("kolibri-theme", theme)
    document.querySelector('meta[name="theme-color"]')?.setAttribute("content", resolvedTheme === "dark" ? "#0a0a0f" : "#f0f4f8")
  }, [theme, resolvedTheme])

  return { theme, setTheme, resolvedTheme }
}
