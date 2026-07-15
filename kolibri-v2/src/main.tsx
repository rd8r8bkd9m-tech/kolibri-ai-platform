import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router'
import './index.css'
import App from './App'
import { disableLegacyServiceWorker } from './platform/disableLegacyServiceWorker'
import { initializeKolibriTheme } from './features/shell/theme'
import { LocaleProvider } from './features/localization'
import { publishBuildReleaseIdentity } from './features/shell/releaseIdentity'

initializeKolibriTheme()
publishBuildReleaseIdentity()

const publicBase = import.meta.env.BASE_URL
const routerBasename = publicBase === '/' ? undefined : publicBase.replace(/\/$/, '')

// The first production release is deliberately network-first. Older Kolibri
// builds registered a cache-first service worker which could keep serving the
// retired shell after an atomic release switch.
disableLegacyServiceWorker()

createRoot(document.getElementById('root')!).render(
  <BrowserRouter basename={routerBasename}>
    <LocaleProvider>
      <App />
    </LocaleProvider>
  </BrowserRouter>
)
