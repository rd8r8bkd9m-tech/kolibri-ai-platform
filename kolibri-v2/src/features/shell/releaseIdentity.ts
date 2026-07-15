const OWNER_ROLES = new Set(['admin', 'owner', 'superadmin'])
const RELEASE_ID_PATTERN = /^[a-z0-9][a-z0-9._-]{0,95}$/i

type BuildReleaseIdentityTarget = typeof globalThis & {
  KOLIBRI_RELEASE_ID?: string
  document?: Document
}

export function isOwnerRole(role: string | undefined): boolean {
  return OWNER_ROLES.has(role?.trim().toLowerCase() ?? '')
}

export function safeBuildReleaseId(value: string | undefined): string | null {
  const normalized = value?.trim()
  return normalized && RELEASE_ID_PATTERN.test(normalized) ? normalized : null
}

export const KOLIBRI_BUILD_RELEASE_ID = safeBuildReleaseId(import.meta.env.VITE_KOLIBRI_RELEASE_ID)

export function publishBuildReleaseIdentity(
  target: BuildReleaseIdentityTarget = globalThis as BuildReleaseIdentityTarget,
  releaseId: string | null = KOLIBRI_BUILD_RELEASE_ID,
): string | null {
  const safeReleaseId = safeBuildReleaseId(releaseId ?? undefined)
  if (!safeReleaseId) return null

  Object.defineProperty(target, 'KOLIBRI_RELEASE_ID', {
    value: safeReleaseId,
    configurable: true,
    enumerable: true,
    writable: false,
  })
  target.document?.documentElement?.setAttribute('data-kolibri-release-id', safeReleaseId)
  return safeReleaseId
}
