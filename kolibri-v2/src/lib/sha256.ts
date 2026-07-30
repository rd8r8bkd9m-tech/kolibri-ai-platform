import { sha256 } from '@noble/hashes/sha2.js'
import { bytesToHex } from '@noble/hashes/utils.js'

/**
 * Hash artifact bytes in both secure production contexts and HTTP LAN dev.
 * Web Crypto remains the preferred native route; the audited noble fallback
 * keeps integrity verification enabled when browsers intentionally omit
 * crypto.subtle outside HTTPS/localhost.
 */
export async function sha256Hex(
  bytes: ArrayBuffer,
  subtle: SubtleCrypto | undefined = globalThis.crypto?.subtle,
): Promise<string> {
  if (subtle) {
    try {
      return bytesToHex(new Uint8Array(await subtle.digest('SHA-256', bytes)))
    } catch {
      // A present-but-disabled Web Crypto implementation must not turn hash
      // verification into a feature flag. The software path verifies the
      // same exact bytes below.
    }
  }
  return bytesToHex(sha256(new Uint8Array(bytes)))
}
