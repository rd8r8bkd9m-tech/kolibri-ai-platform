import { createRoot } from 'react-dom/client'
import { HashRouter } from 'react-router'
import './index.css'
import App from './App'

const normalizeDirectRoute = () => {
  const { pathname, search, hash } = window.location
  if (hash && hash !== '#') return

  const routeNames = new Set([
    'agents',
    'apps',
    'chat',
    'documents',
    'estimates',
    'library',
    'login',
    'servers',
    'settings',
  ])
  const parts = pathname.split('/').filter(Boolean)
  const route = parts[0] === 'dashboard' ? parts[1] : parts[0]
  if (!route) return

  const normalizedRoute = routeNames.has(route) ? `/${route}` : '/'
  window.location.replace(`/#${normalizedRoute}${search}`)
}

normalizeDirectRoute()

const savedTheme = localStorage.getItem('kolibri-theme') || 'light'
if (savedTheme === 'dark' || (savedTheme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
  document.documentElement.classList.add('dark')
}

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register(`${import.meta.env.BASE_URL}sw.js`).catch(() => {})
  })
}

createRoot(document.getElementById('root')!).render(
  <HashRouter>
    <App />
  </HashRouter>
)
