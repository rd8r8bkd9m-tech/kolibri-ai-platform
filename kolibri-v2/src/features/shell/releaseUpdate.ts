import { KOLIBRI_BUILD_RELEASE_ID, safeBuildReleaseId } from './releaseIdentity'

const MODULE_SCRIPT = /<script\b(?=[^>]*\btype=["']module["'])(?=[^>]*\bsrc=["']([^"']+)["'])[^>]*>/i
export const RELEASE_PROBE_TIMEOUT_MS = 10_000

export function moduleAssetFromHtml(html: string): string | null {
  return MODULE_SCRIPT.exec(html)?.[1] ?? null
}

export function activeModuleAsset(root: ParentNode = document): string | null {
  return root.querySelector<HTMLScriptElement>('script[type="module"][src]')?.getAttribute('src') ?? null
}

function assetPath(asset: string, origin: string): string | null {
  try {
    const url = new URL(asset, origin)
    return `${url.pathname}${url.search}`
  } catch {
    return null
  }
}

export async function frontendUpdateAvailable(
  currentAsset: string,
  fetcher: typeof fetch = fetch,
  origin: string = window.location.origin,
  timeoutMs: number = RELEASE_PROBE_TIMEOUT_MS,
  currentReleaseId: string | null = KOLIBRI_BUILD_RELEASE_ID,
  frontendRoot: string = import.meta.env.BASE_URL || '/',
): Promise<boolean> {
  const controller = new AbortController()
  const timeout = globalThis.setTimeout(() => controller.abort(), Math.max(1, timeoutMs))
  try {
    const response = await fetcher(frontendRoot, {
      method: 'GET',
      cache: 'no-store',
      credentials: 'same-origin',
      headers: { Accept: 'text/html' },
      signal: controller.signal,
    })
    if (!response.ok) return false
    const safeCurrentReleaseId = safeBuildReleaseId(currentReleaseId ?? undefined)
    const candidateReleaseId = safeBuildReleaseId(response.headers.get('X-Kolibri-Release') ?? undefined)
    if (safeCurrentReleaseId && candidateReleaseId) return safeCurrentReleaseId !== candidateReleaseId
    const candidate = moduleAssetFromHtml(await response.text())
    const currentPath = assetPath(currentAsset, origin)
    const candidatePath = candidate ? assetPath(candidate, origin) : null
    return Boolean(currentPath && candidatePath && currentPath !== candidatePath)
  } finally {
    globalThis.clearTimeout(timeout)
  }
}
