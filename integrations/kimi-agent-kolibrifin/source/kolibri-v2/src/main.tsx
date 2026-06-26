import { createRoot } from 'react-dom/client'
import { HashRouter } from 'react-router'
import './index.css'
import App from './App'

createRoot(document.getElementById('root')!).render(
  <HashRouter>
    <App />
  </HashRouter>
)
