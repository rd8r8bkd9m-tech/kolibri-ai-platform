import { lazy, Suspense, useState, useEffect } from 'react'
import { Navigate, Routes, Route } from 'react-router'
import Layout from './components/Layout'
import ErrorBoundary from './components/ErrorBoundary'
import AppShellEntry from '@/features/projects/AppShellEntry'
import { auth, getAuthToken, setAuthToken, type AuthUser } from '@/lib/api'
import { useLocale } from '@/features/localization'
import ReleaseUpdateController from '@/features/shell/ReleaseUpdateController'
import ProtectedOwnerRoute from '@/features/auth/ProtectedOwnerRoute'
import ShellBootstrapBoundary from '@/features/auth/ShellBootstrapBoundary'

const PublicLanding = lazy(() => import('./pages/PublicLanding'))
const ChatPage = lazy(() => import('./pages/ChatPage'))
const LibraryPage = lazy(() => import('./pages/LibraryPage'))
const EstimatesPage = lazy(() => import('./pages/EstimatesPage'))
const DocumentsPage = lazy(() => import('./pages/DocumentsPage'))
const AgentsPage = lazy(() => import('./pages/AgentsPage'))
const ServersPage = lazy(() => import('./pages/ServersPage'))
const SettingsPage = lazy(() => import('./pages/SettingsPage'))
const LoginPage = lazy(() => import('./pages/LoginPage'))
const DevelopersPage = lazy(() => import('./pages/DevelopersPage'))
const DeveloperDocsPage = lazy(() => import('./pages/DeveloperDocsPage'))
const DeveloperPlaygroundPage = lazy(() => import('./pages/DeveloperPlaygroundPage'))

export default function App() {
  const { t } = useLocale()
  const [user, setUser] = useState<AuthUser | null>(null)
  const [checking, setChecking] = useState(() => Boolean(getAuthToken()))

  useEffect(() => {
    if (!getAuthToken()) return

    let active = true
    auth.me()
      .then(u => { if (active) setUser(u) })
      .catch(() => { setAuthToken(null) })
      .finally(() => { if (active) setChecking(false) })

    return () => { active = false }
  }, [])

  return (
    <>
      <ReleaseUpdateController />
      {checking ? (
        <div className="flex items-center justify-center h-[100dvh] text-[var(--text-tertiary)]">{t('app.loading')}</div>
      ) : (
        <Suspense fallback={<div className="flex items-center justify-center h-[100dvh] text-[var(--text-tertiary)]">{t('app.loading')}</div>}>
          <Routes>
            <Route index element={<ErrorBoundary><PublicLanding /></ErrorBoundary>} />
            <Route path="login" element={<LoginPage onLogin={setUser} />} />
            <Route element={<ShellBootstrapBoundary />}>
              <Route element={<ErrorBoundary><Layout user={user} /></ErrorBoundary>}>
                <Route path="app" element={<AppShellEntry />} />
                <Route path="chat" element={<ChatPage />} />
                <Route path="chat/:projectId" element={<ChatPage />} />
                <Route path="library" element={<LibraryPage />} />
                <Route path="apps" element={<Navigate to="/app" replace />} />
                <Route path="estimates" element={<EstimatesPage />} />
                <Route path="documents" element={<DocumentsPage />} />
                <Route path="agents" element={<ProtectedOwnerRoute user={user}><AgentsPage /></ProtectedOwnerRoute>} />
                <Route path="control" element={<ProtectedOwnerRoute user={user}><AgentsPage /></ProtectedOwnerRoute>} />
                <Route path="servers" element={<ProtectedOwnerRoute user={user}><ServersPage /></ProtectedOwnerRoute>} />
                <Route path="developers" element={<DevelopersPage user={user} />} />
                <Route path="docs" element={<DeveloperDocsPage />} />
                <Route path="playground" element={<DeveloperPlaygroundPage />} />
                <Route path="settings" element={<SettingsPage user={user} onLogout={() => { setUser(null); setAuthToken(null) }} />} />
              </Route>
            </Route>
          </Routes>
        </Suspense>
      )}
    </>
  )
}
