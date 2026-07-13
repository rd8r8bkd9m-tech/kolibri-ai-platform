// Tombstone for the retired cache-first worker. PWA caching will return only
// after it has its own release gate and cannot pin an obsolete Kolibri shell.
self.addEventListener('install', () => self.skipWaiting())

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const keys = await caches.keys()
    await Promise.all(
      keys.filter((key) => key.startsWith('kolibri-')).map((key) => caches.delete(key)),
    )
    await self.registration.unregister()
    const clients = await self.clients.matchAll({ type: 'window' })
    clients.forEach((client) => client.navigate(client.url))
  })())
})
