const LEGACY_CACHE_PREFIX = 'kolibri-'

export function disableLegacyServiceWorker() {
  if ('serviceWorker' in navigator) {
    void navigator.serviceWorker.getRegistrations().then((registrations) =>
      Promise.all(registrations.map((registration) => registration.unregister())),
    )
  }

  if ('caches' in window) {
    void caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key.startsWith(LEGACY_CACHE_PREFIX))
          .map((key) => caches.delete(key)),
      ),
    )
  }
}
