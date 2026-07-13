import { createRoot } from 'react-dom/client'
import { HashRouter } from 'react-router'
import './index.css'
import App from './App'
import { disableLegacyServiceWorker } from './platform/disableLegacyServiceWorker'

const savedTheme = localStorage.getItem('kolibri-theme') || 'light'
if (savedTheme === 'dark' || (savedTheme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
  document.documentElement.classList.add('dark')
}

// The first production release is deliberately network-first. Older Kolibri
// builds registered a cache-first service worker which could keep serving the
// retired shell after an atomic release switch.
disableLegacyServiceWorker()

createRoot(document.getElementById('root')!).render(
  <HashRouter>
    <App />
  </HashRouter>
)
