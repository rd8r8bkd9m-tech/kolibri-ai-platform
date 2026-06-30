const LOCAL_HOSTS = new Set(["localhost", "127.0.0.1", "[::1]"])

export function registerServiceWorker() {
  if (!("serviceWorker" in navigator) || !import.meta.env.PROD) return

  const canRegister = window.isSecureContext || LOCAL_HOSTS.has(window.location.hostname)
  if (!canRegister) return

  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {})
  })
}
