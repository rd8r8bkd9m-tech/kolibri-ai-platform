import { createRoot } from 'react-dom/client'
import { HashRouter } from 'react-router'
import './index.css'
import App from './App'
import { disableLegacyServiceWorker } from './platform/disableLegacyServiceWorker'
import { initializeKolibriTheme } from './features/shell/theme'
import { LocaleProvider } from './features/localization'

initializeKolibriTheme()

// The first production release is deliberately network-first. Older Kolibri
// builds registered a cache-first service worker which could keep serving the
// retired shell after an atomic release switch.
disableLegacyServiceWorker()

createRoot(document.getElementById('root')!).render(
  <HashRouter>
    <LocaleProvider>
      <App />
    </LocaleProvider>
  </HashRouter>
)
