/* Garage Gate service worker.
 * Rendered by Flask (app.admin.service_worker) so the cache version and asset
 * URLs stay in sync with the deployed build. Bump CACHE by changing the app
 * version below or the template — clients pick up the new worker automatically.
 */
const CACHE = "gate-{{ sw_version }}";

// App shell that is safe to serve from cache. The gate-open flow always hits
// the network, so we only precache static, auth-free assets plus the offline
// fallback shown when a navigation cannot reach the server.
const PRECACHE = [
  "{{ url_for('static', filename='icons/icon-192.png') }}",
  "{{ url_for('static', filename='icons/icon-512.png') }}",
  "{{ url_for('static', filename='icons/icon-maskable-512.png') }}",
  "{{ url_for('static', filename='icons/apple-touch-icon.png') }}",
  "{{ url_for('admin.offline') }}",
  "{{ url_for('admin.manifest') }}",
];

const OFFLINE_URL = "{{ url_for('admin.offline') }}";

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(PRECACHE)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return; // never cache gate-open POSTs

  // Navigations: network-first, fall back to the offline page when unreachable.
  if (req.mode === "navigate") {
    event.respondWith(
      fetch(req).catch(() => caches.match(OFFLINE_URL))
    );
    return;
  }

  // Static assets: cache-first, then network (and cache the result).
  const url = new URL(req.url);
  if (url.origin === self.location.origin && url.pathname.startsWith("{{ static_prefix }}")) {
    event.respondWith(
      caches.match(req).then((hit) => hit || fetch(req).then((resp) => {
        const copy = resp.clone();
        caches.open(CACHE).then((cache) => cache.put(req, copy));
        return resp;
      }))
    );
  }
});
