const OWNER_ROLES = new Set(['admin', 'owner', 'superadmin'])
const RELEASE_ID_PATTERN = /^[a-z0-9][a-z0-9._-]{0,95}$/i

export function isOwnerRole(role: string | undefined): boolean {
  return OWNER_ROLES.has(role?.trim().toLowerCase() ?? '')
}

export function safeBuildReleaseId(value: string | undefined): string | null {
  const normalized = value?.trim()
  return normalized && RELEASE_ID_PATTERN.test(normalized) ? normalized : null
}

export const KOLIBRI_BUILD_RELEASE_ID = safeBuildReleaseId(import.meta.env.VITE_KOLIBRI_RELEASE_ID)
