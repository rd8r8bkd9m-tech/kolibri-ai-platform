import { isOwnerRole } from '@/features/shell/releaseIdentity'
import type { AuthUser } from '@/lib/api'

export function ownerRouteTarget(user: AuthUser | null): string | null {
  if (!user) return '/login'
  return isOwnerRole(user.role) ? null : '/'
}
