/* The panel moved from /admin/ to /. This replaces the old /admin/ service
 * worker: it clears its caches, unregisters itself and reloads open windows so
 * they land on the new root page (which registers the new worker). */
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.map((k) => caches.delete(k))))
      .then(() => self.registration.unregister())
      .then(() => self.clients.matchAll({ type: "window" }))
      .then((clients) => clients.forEach((c) => c.navigate("/")))
  );
});
