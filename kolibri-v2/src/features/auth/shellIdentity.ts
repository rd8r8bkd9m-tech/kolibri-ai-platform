import type { AuthUser } from '@/lib/api'

export interface ShellOutletContext {
  user: AuthUser | null
}

function normalizedName(user: AuthUser | null | undefined): string {
  return typeof user?.name === 'string'
    ? user.name.trim().replace(/\s+/g, ' ')
    : ''
}

/** Only the user returned by the verified /auth/session probe may personalize UI. */
export function verifiedDisplayName(user: AuthUser | null | undefined): string | null {
  return normalizedName(user) || null
}

export function verifiedFirstName(user: AuthUser | null | undefined): string | null {
  const displayName = normalizedName(user)
  return displayName ? displayName.split(' ')[0] : null
}

export function verifiedInitials(user: AuthUser | null | undefined): string | null {
  const displayName = normalizedName(user)
  if (!displayName) return null
  return displayName
    .split(' ')
    .slice(0, 2)
    .map(part => Array.from(part)[0] ?? '')
    .join('')
    .toLocaleUpperCase()
}
