import { translations, type TranslationKey } from './translations'

export const LOCALE_STORAGE_KEY = 'kolibri-language'
export const supportedLocales = ['ru', 'en'] as const
export type Locale = (typeof supportedLocales)[number]

export interface LocaleStorage {
  getItem: (key: string) => string | null
  setItem: (key: string, value: string) => void
}

export function isSupportedLocale(value: unknown): value is Locale {
  return typeof value === 'string' && supportedLocales.includes(value as Locale)
}

export function resolveLocale(value: unknown): Locale {
  return isSupportedLocale(value) ? value : 'ru'
}

export function readStoredLocale(storage?: LocaleStorage | null): Locale {
  if (!storage) return 'ru'
  try {
    return resolveLocale(storage.getItem(LOCALE_STORAGE_KEY))
  } catch {
    return 'ru'
  }
}

export function writeStoredLocale(locale: Locale, storage?: LocaleStorage | null): void {
  if (!storage) return
  try {
    storage.setItem(LOCALE_STORAGE_KEY, locale)
  } catch {
    // The visible locale still changes when storage is unavailable.
  }
}

export function applyDocumentLocale(locale: Locale, root?: { lang: string } | null): void {
  if (root) root.lang = locale
}

export type TranslationParams = Record<string, string | number>

export function translate(locale: Locale, key: TranslationKey, params: TranslationParams = {}): string {
  return Object.entries(params).reduce(
    (text, [name, value]) => text.replaceAll(`{${name}}`, String(value)),
    translations[locale][key],
  )
}

const traceSummaryKeys: TranslationKey[] = [
  'trace.estimateSaving',
  'trace.estimateSaved',
  'trace.estimateSaveFailed',
  'trace.documentSaving',
  'trace.documentSaved',
  'trace.documentSaveFailed',
  'trace.imageVerificationFailed',
  'trace.routeRetrying',
  'trace.routeFailed',
  'trace.cancelledByUser',
]

export function translateKnownTraceSummary(locale: Locale, summary: string): string {
  const key = traceSummaryKeys.find(candidate => supportedLocales.some(sourceLocale => (
    translations[sourceLocale][candidate] === summary
  )))
  return key ? translations[locale][key] : summary
}

export type Translate = (key: TranslationKey, params?: TranslationParams) => string
