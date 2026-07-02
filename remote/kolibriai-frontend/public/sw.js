const CACHE_NAME = 'kolibri-v2-mobile-shell-20260628-4'
const STATIC_ASSETS = [
  '/',
  '/index.html',
  '/kolibri-bird.png',
  '/manifest.json',
]

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS))
  )
  self.skipWaiting()
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  )
  self.clients.claim()
})

self.addEventListener('fetch', (event) => {
  const { request } = event
  if (request.method !== 'GET') return
  if (request.url.includes('/api/')) return

  const acceptHeader = request.headers.get('accept') || ''
  const isNavigationRequest = request.mode === 'navigate' || acceptHeader.includes('text/html')

  event.respondWith(
    caches.match(request).then((cached) => {
      if (isNavigationRequest) {
        return fetch(request)
          .then((response) => {
            if (response.ok) {
              const clone = response.clone()
              caches.open(CACHE_NAME).then((cache) => cache.put(request, clone))
            }
            return response
          })
          .catch(() => {
            return cached || caches.match('/index.html')
          })
      }

      const fetchPromise = fetch(request).then((response) => {
        if (response.ok) {
          const clone = response.clone()
          caches.open(CACHE_NAME).then((cache) => cache.put(request, clone))
        }
        return response
      }).catch(() => cached)
      return cached || fetchPromise
    })
  )
})
