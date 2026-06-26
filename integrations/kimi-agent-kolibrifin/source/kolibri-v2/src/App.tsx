import { Routes, Route } from 'react-router'
import Layout from './components/Layout'
import Home from './pages/Home'
import ChatPage from './pages/ChatPage'
import LibraryPage from './pages/LibraryPage'
import AppsPage from './pages/AppsPage'
import EstimatesPage from './pages/EstimatesPage'
import DocumentsPage from './pages/DocumentsPage'
import AgentsPage from './pages/AgentsPage'
import ServersPage from './pages/ServersPage'
import SettingsPage from './pages/SettingsPage'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Home />} />
        <Route path="chat" element={<ChatPage />} />
        <Route path="library" element={<LibraryPage />} />
        <Route path="apps" element={<AppsPage />} />
        <Route path="estimates" element={<EstimatesPage />} />
        <Route path="documents" element={<DocumentsPage />} />
        <Route path="agents" element={<AgentsPage />} />
        <Route path="servers" element={<ServersPage />} />
        <Route path="settings" element={<SettingsPage />} />
      </Route>
    </Routes>
  )
}
