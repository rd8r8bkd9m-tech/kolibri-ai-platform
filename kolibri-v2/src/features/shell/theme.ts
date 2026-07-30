export type KolibriTheme = 'light' | 'dark' | 'system'

export const KOLIBRI_THEME_KEY = 'kolibri-theme'

export function getStoredTheme(): KolibriTheme {
  const current = localStorage.getItem(KOLIBRI_THEME_KEY)
  if (current === 'light' || current === 'dark' || current === 'system') return current
  const legacy = localStorage.getItem('kolibri-v21-theme')
  if (legacy === 'dark' || legacy === 'system') return legacy
  return 'light'
}

export function resolveTheme(theme: KolibriTheme): 'light' | 'dark' {
  if (theme === 'system') return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  return theme
}

export function applyKolibriTheme(theme: KolibriTheme, persist = true) {
  const resolved = resolveTheme(theme)
  document.documentElement.classList.toggle('dark', resolved === 'dark')
  document.documentElement.dataset.theme = resolved
  document.documentElement.style.colorScheme = resolved
  document.querySelector<HTMLMetaElement>('meta[name="theme-color"]')?.setAttribute('content', resolved === 'dark' ? '#101112' : '#ffffff')
  if (persist) localStorage.setItem(KOLIBRI_THEME_KEY, theme)
  window.dispatchEvent(new CustomEvent('kolibri:theme-change', { detail: { theme, resolved } }))
}

export function initializeKolibriTheme() {
  applyKolibriTheme(getStoredTheme(), false)
  const media = window.matchMedia('(prefers-color-scheme: dark)')
  const syncSystemTheme = () => {
    if (getStoredTheme() === 'system') applyKolibriTheme('system', false)
  }
  media.addEventListener('change', syncSystemTheme)
}
