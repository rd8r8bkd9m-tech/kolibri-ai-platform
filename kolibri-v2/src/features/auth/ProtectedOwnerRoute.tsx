import type { ReactNode } from 'react'
import { Navigate } from 'react-router'
import { ownerRouteTarget } from './ownerAccess'
import type { AuthUser } from '@/lib/api'

export default function ProtectedOwnerRoute({ user, children }: { user: AuthUser | null; children: ReactNode }) {
  const target = ownerRouteTarget(user)
  return target ? <Navigate to={target} replace /> : children
}
