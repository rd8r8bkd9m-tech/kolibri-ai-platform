import { describe, expect, it, vi } from 'vitest'
import { frontendUpdateAvailable, moduleAssetFromHtml } from './releaseUpdate'

describe('frontend release update detection', () => {
  it('extracts only the module entry asset', () => {
    expect(moduleAssetFromHtml('<script type="module" crossorigin src="/assets/index-new.js"></script>'))
      .toBe('/assets/index-new.js')
    expect(moduleAssetFromHtml('<script src="/legacy.js"></script>')).toBeNull()
  })

  it('detects a changed hashed bundle and ignores the same bundle', async () => {
    const changed = vi.fn().mockImplementation(async () => new Response(
      '<script type="module" src="/assets/index-new.js"></script>',
      { status: 200 },
    ))
    await expect(frontendUpdateAvailable('/assets/index-old.js', changed, 'https://kolibriai.ru'))
      .resolves.toBe(true)
    await expect(frontendUpdateAvailable('/assets/index-new.js', changed, 'https://kolibriai.ru'))
      .resolves.toBe(false)
    expect(changed).toHaveBeenCalledWith('/', expect.objectContaining({ cache: 'no-store' }))
  })

  it('fails closed for an unavailable or malformed release document', async () => {
    const unavailable = vi.fn().mockResolvedValue(new Response('', { status: 503 }))
    const malformed = vi.fn().mockResolvedValue(new Response('<html></html>', { status: 200 }))
    await expect(frontendUpdateAvailable('/assets/index-old.js', unavailable, 'https://kolibriai.ru'))
      .resolves.toBe(false)
    await expect(frontendUpdateAvailable('/assets/index-old.js', malformed, 'https://kolibriai.ru'))
      .resolves.toBe(false)
  })

  it('uses a valid release header before falling back to the module asset', async () => {
    const newerRelease = vi.fn().mockResolvedValue(new Response(
      '<script type="module" src="/assets/index-same.js"></script>',
      { status: 200, headers: { 'X-Kolibri-Release': 'kolibri-r18' } },
    ))
    await expect(frontendUpdateAvailable(
      '/assets/index-same.js',
      newerRelease,
      'https://kolibriai.ru',
      1_000,
      'kolibri-r17',
    )).resolves.toBe(true)

    const invalidHeader = vi.fn().mockResolvedValue(new Response(
      '<script type="module" src="/assets/index-new.js"></script>',
      { status: 200, headers: { 'X-Kolibri-Release': '<unsafe>' } },
    ))
    await expect(frontendUpdateAvailable(
      '/assets/index-old.js',
      invalidHeader,
      'https://kolibriai.ru',
      1_000,
      'kolibri-r17',
    )).resolves.toBe(true)
  })

  it('does not report an update when both valid release identities match', async () => {
    const sameRelease = vi.fn().mockResolvedValue(new Response(
      '<script type="module" src="/assets/index-different.js"></script>',
      { status: 200, headers: { 'X-Kolibri-Release': 'kolibri-r17' } },
    ))
    await expect(frontendUpdateAvailable(
      '/assets/index-old.js',
      sameRelease,
      'https://kolibriai.ru',
      1_000,
      'kolibri-r17',
    )).resolves.toBe(false)
  })

  it('aborts a stalled release probe so later checks can run', async () => {
    vi.useFakeTimers()
    try {
      const stalled = vi.fn((_: RequestInfo | URL, init?: RequestInit) => new Promise<Response>((_, reject) => {
        init?.signal?.addEventListener('abort', () => {
          reject(new DOMException('Probe timed out', 'AbortError'))
        })
      }))
      const probe = frontendUpdateAvailable(
        '/assets/index-old.js',
        stalled,
        'https://kolibriai.ru',
        25,
      )
      const rejection = expect(probe).rejects.toMatchObject({ name: 'AbortError' })

      await vi.advanceTimersByTimeAsync(25)
      await rejection
      expect(stalled.mock.calls[0]?.[1]?.signal?.aborted).toBe(true)
    } finally {
      vi.useRealTimers()
    }
  })
})
