const CACHE_NAME = "kolibri-v3-shell-v1"
const SHELL_URLS = ["/", "/manifest.webmanifest", "/kolibri-mascot.png"]

self.addEventListener("install", event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(SHELL_URLS)).then(() => self.skipWaiting()),
  )
})

self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(key => key !== CACHE_NAME).map(key => caches.delete(key))))
      .then(() => self.clients.claim()),
  )
})

self.addEventListener("fetch", event => {
  const request = event.request
  const url = new URL(request.url)

  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/v1/")) {
    event.respondWith(apiFetch(request))
    return
  }

  if (request.mode === "navigate") {
    event.respondWith(networkFirstShell(request))
    return
  }

  if (request.method === "GET" && url.origin === self.location.origin) {
    event.respondWith(cacheFirst(request))
  }
})

async function apiFetch(request) {
  try {
    return await fetch(request)
  } catch {
    return new Response(JSON.stringify({
      code: "backend_offline",
      message: "Backend недоступен. Черновик остается локально, повторите действие после подключения.",
    }), {
      status: 502,
      headers: { "Content-Type": "application/json" },
    })
  }
}

async function networkFirstShell(request) {
  const cache = await caches.open(CACHE_NAME)
  try {
    const response = await fetch(request)
    if (response.ok) {
      cache.put("/", response.clone())
    }
    return response
  } catch {
    return (await cache.match("/")) || Response.error()
  }
}

async function cacheFirst(request) {
  const cached = await caches.match(request)
  if (cached) return cached
  const response = await fetch(request)
  if (response.ok) {
    const cache = await caches.open(CACHE_NAME)
    cache.put(request, response.clone())
  }
  return response
}
