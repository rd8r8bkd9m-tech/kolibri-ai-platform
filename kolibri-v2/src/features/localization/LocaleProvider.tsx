import { useCallback, useEffect, useLayoutEffect, useMemo, useState, type PropsWithChildren } from 'react'
import { LocaleContext } from './localeContext'
import { LOCALE_STORAGE_KEY, applyDocumentLocale, readStoredLocale, resolveLocale, translate, writeStoredLocale, type Locale } from './locale'

export function LocaleProvider({ children }: PropsWithChildren) {
  const [locale, setLocaleState] = useState<Locale>(() => readStoredLocale(
    typeof window === 'undefined' ? null : window.localStorage,
  ))

  const setLocale = useCallback((next: Locale) => {
    const safeLocale = resolveLocale(next)
    setLocaleState(safeLocale)
    writeStoredLocale(safeLocale, typeof window === 'undefined' ? null : window.localStorage)
  }, [])

  useLayoutEffect(() => {
    applyDocumentLocale(locale, document.documentElement)
  }, [locale])

  useEffect(() => {
    const syncLocale = (event: StorageEvent) => {
      if (event.key === LOCALE_STORAGE_KEY) setLocaleState(resolveLocale(event.newValue))
    }
    window.addEventListener('storage', syncLocale)
    return () => window.removeEventListener('storage', syncLocale)
  }, [])

  const value = useMemo(() => ({
    locale,
    setLocale,
    t: (key: Parameters<typeof translate>[1], params?: Parameters<typeof translate>[2]) => translate(locale, key, params),
  }), [locale, setLocale])

  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>
}
