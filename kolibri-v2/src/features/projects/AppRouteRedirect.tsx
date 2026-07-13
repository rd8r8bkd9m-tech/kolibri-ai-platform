import { Navigate, useLocation } from 'react-router'
import { appRouteTarget } from './appRoute'

export default function AppRouteRedirect() {
  const { search } = useLocation()
  return <Navigate to={appRouteTarget(search)} replace />
}
