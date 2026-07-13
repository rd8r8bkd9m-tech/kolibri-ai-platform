import { useState, useEffect } from 'react'
import { Routes, Route } from 'react-router'
import Layout from './components/Layout'
import ErrorBoundary from './components/ErrorBoundary'
import Home from './pages/Home'
import ChatPage from './pages/ChatPage'
import LibraryPage from './pages/LibraryPage'
import AppsPage from './pages/AppsPage'
import EstimatesPage from './pages/EstimatesPage'
import DocumentsPage from './pages/DocumentsPage'
import AgentsPage from './pages/AgentsPage'
import ServersPage from './pages/ServersPage'
import SettingsPage from './pages/SettingsPage'
import LoginPage from './pages/LoginPage'
import { auth, getAuthToken, type AuthUser } from '@/lib/api'

export default function App() {
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
    return <div className="flex items-center justify-center h-[100dvh] text-[var(--text-tertiary)]">Загрузка...</div>
  }

  return (
    <Routes>
      <Route path="login" element={<LoginPage onLogin={setUser} />} />
      <Route element={<ErrorBoundary><Layout user={user} onLogout={() => { setUser(null); localStorage.removeItem('kolibri_token') }} /></ErrorBoundary>}>
        <Route index element={<Home />} />
        <Route path="chat" element={<ChatPage />} />
        <Route path="library" element={<LibraryPage />} />
        <Route path="apps" element={<AppsPage />} />
        <Route path="estimates" element={<EstimatesPage />} />
        <Route path="documents" element={<DocumentsPage />} />
        <Route path="agents" element={<AgentsPage />} />
        <Route path="servers" element={<ServersPage />} />
        <Route path="settings" element={<SettingsPage user={user} onLogout={() => { setUser(null); localStorage.removeItem('kolibri_token') }} />} />
      </Route>
    </Routes>
  )
}
