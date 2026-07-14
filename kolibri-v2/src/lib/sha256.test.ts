import { describe, expect, it, vi } from 'vitest'
import { sha256Hex } from './sha256'

describe('sha256Hex', () => {
  const bytes = new TextEncoder().encode('kolibri').buffer
  const expected = 'b8ac4d9e937638ef2dc9276b8ec0d479bab7b9a16ad01358431a61857687f0f2'

  it('verifies bytes without Web Crypto in an HTTP LAN context', async () => {
    await expect(sha256Hex(bytes, undefined)).resolves.toBe(expected)
  })

  it('falls back without weakening verification when native digest rejects', async () => {
    const subtle = { digest: vi.fn().mockRejectedValue(new Error('insecure context')) } as unknown as SubtleCrypto
    await expect(sha256Hex(bytes, subtle)).resolves.toBe(expected)
  })
})
