import { useState, useEffect } from 'react'
import { Navigate, Routes, Route } from 'react-router'
import Layout from './components/Layout'
import ErrorBoundary from './components/ErrorBoundary'
import Home from './pages/Home'
import ChatPage from './pages/ChatPage'
import LibraryPage from './pages/LibraryPage'
import EstimatesPage from './pages/EstimatesPage'
import DocumentsPage from './pages/DocumentsPage'
import AgentsPage from './pages/AgentsPage'
import ServersPage from './pages/ServersPage'
import SettingsPage from './pages/SettingsPage'
import LoginPage from './pages/LoginPage'
import DevelopersPage from './pages/DevelopersPage'
import DeveloperDocsPage from './pages/DeveloperDocsPage'
import DeveloperPlaygroundPage from './pages/DeveloperPlaygroundPage'
import { auth, getAuthToken, type AuthUser } from '@/lib/api'
import { useLocale } from '@/features/localization'

export default function App() {
  const { t } = useLocale()
  const [user, setUser] = useState<AuthUser | null>(null)
  const [checking, setChecking] = useState(() => Boolean(getAuthToken()))

  useEffect(() => {
    if (!getAuthToken()) return

    let active = true
    auth.me()
      .then(u => { if (active) setUser(u) })
      .catch(() => { localStorage.removeItem('kolibri_token') })
      .finally(() => { if (active) setChecking(false) })

    return () => { active = false }
  }, [])

  if (checking) {
    return <div className="flex items-center justify-center h-[100dvh] text-[var(--text-tertiary)]">{t('app.loading')}</div>
  }

  return (
    <Routes>
      <Route path="login" element={<LoginPage onLogin={setUser} />} />
      <Route element={<ErrorBoundary><Layout /></ErrorBoundary>}>
        <Route index element={<Home />} />
        <Route path="chat" element={<ChatPage />} />
        <Route path="chat/:projectId" element={<ChatPage />} />
        <Route path="library" element={<LibraryPage />} />
        <Route path="apps" element={<Navigate to="/chat" replace />} />
        <Route path="estimates" element={<EstimatesPage />} />
        <Route path="documents" element={<DocumentsPage />} />
        <Route path="agents" element={<AgentsPage />} />
        <Route path="control" element={<AgentsPage />} />
        <Route path="servers" element={<ServersPage />} />
        <Route path="developers" element={<DevelopersPage user={user} />} />
        <Route path="docs" element={<DeveloperDocsPage />} />
        <Route path="playground" element={<DeveloperPlaygroundPage />} />
        <Route path="settings" element={<SettingsPage user={user} onLogout={() => { setUser(null); localStorage.removeItem('kolibri_token') }} />} />
      </Route>
    </Routes>
  )
}
