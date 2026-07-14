import { useLocation } from 'react-router'
import Home from '@/pages/Home'
import AppRouteRedirect from './AppRouteRedirect'
import { shouldRedirectAppEntry } from './appShellEntry'

export default function AppShellEntry() {
  const { search, hash } = useLocation()
  return shouldRedirectAppEntry(search, hash) ? <AppRouteRedirect /> : <Home />
}
