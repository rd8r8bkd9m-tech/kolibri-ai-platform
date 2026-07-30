import { describe, expect, it } from 'vitest'
import { LOCALE_STORAGE_KEY, applyDocumentLocale, readStoredLocale, resolveLocale, translate, translateKnownTraceSummary, writeStoredLocale, type LocaleStorage } from './locale'

function memoryStorage(initial?: string): LocaleStorage & { value: string | null } {
  return {
    value: initial ?? null,
    getItem() { return this.value },
    setItem(_key, value) { this.value = value },
  }
}

describe('locale state', () => {
  it('accepts only shipped locales', () => {
    expect(resolveLocale('en')).toBe('en')
    expect(resolveLocale('de')).toBe('ru')
    expect(resolveLocale(null)).toBe('ru')
  })

  it('persists a supported locale and restores it after reload', () => {
    const storage = memoryStorage()
    writeStoredLocale('en', storage)
    expect(storage.value).toBe('en')
    expect(readStoredLocale(storage)).toBe('en')
  })

  it('falls back safely when persisted state is invalid or unavailable', () => {
    expect(readStoredLocale(memoryStorage('unsupported'))).toBe('ru')
    expect(readStoredLocale({
      getItem: () => { throw new Error('blocked') },
      setItem: () => undefined,
    })).toBe('ru')
  })

  it('interpolates translated shell copy', () => {
    expect(translate('en', 'history.deleted', { title: 'House' })).toBe('Project deleted: House')
    expect(translate('ru', 'trace.seconds', { count: 12 })).toBe('12 сек.')
    expect(LOCALE_STORAGE_KEY).toBe('kolibri-language')
  })

  it('updates the document language contract immediately', () => {
    const root = { lang: 'ru' }
    applyDocumentLocale('en', root)
    expect(root.lang).toBe('en')
  })

  it('re-localizes persisted semantic work trace summaries', () => {
    expect(translateKnownTraceSummary('en', 'Смета сохранена в текущем проекте')).toBe('Estimate saved to the current project')
    expect(translateKnownTraceSummary('en', 'Provider-specific message')).toBe('Provider-specific message')
  })
})
