self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => {
  event.waitUntil(
    Promise.all([
      self.caches.keys().then((keys) => Promise.all(keys.map((key) => self.caches.delete(key)))),
      self.registration.unregister(),
      self.clients.claim(),
    ]),
  );
});
