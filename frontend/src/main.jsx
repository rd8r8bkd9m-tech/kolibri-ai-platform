if (!window.crypto || !window.crypto.randomUUID) {
  window.crypto = window.crypto || {};
  window.crypto.randomUUID = function() {
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function(c) {
      var r = Math.random() * 16 | 0, v = c == "x" ? r : (r & 0x3 | 0x8);
      return v.toString(16);
    });
  };
}
import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import "./index.css"
import App from "./App.jsx"

// Remove the legacy kiosk service worker. It cached extension requests and
// kept obsolete API paths alive after the Home-only application release.
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.getRegistrations().then((registrations) => {
    registrations.forEach((registration) => registration.unregister());
  }).catch(() => {});
}
if ("caches" in window) {
  caches.keys().then((keys) => Promise.all(keys.map((key) => caches.delete(key)))).catch(() => {});
}

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
