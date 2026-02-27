const MAP_CACHE = 'autonomous-grid-map-v1';
const ASSET_CACHE = 'autonomous-grid-assets-v1';

const isMapResource = (url) => (
  url.pathname.endsWith('.pmtiles') || url.pathname.endsWith('/map_style_cyberpunk.json')
);

const isStaticAsset = (url) => (
  url.pathname.endsWith('.js') ||
  url.pathname.endsWith('.css')
);

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(MAP_CACHE).then((cache) => cache.addAll(['/map_style_cyberpunk.json'])),
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(
      keys
        .filter((key) => ![MAP_CACHE, ASSET_CACHE].includes(key))
        .map((key) => caches.delete(key)),
    )),
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.method !== 'GET') return;

  const url = new URL(request.url);

  if (isMapResource(url)) {
    event.respondWith(
      caches.open(MAP_CACHE).then(async (cache) => {
        const cached = await cache.match(request);
        if (cached) return cached;

        const response = await fetch(request);
        if (response && response.ok) {
          cache.put(request, response.clone());
        }
        return response;
      }),
    );
    return;
  }

  if (isStaticAsset(url)) {
    event.respondWith(
      caches.open(ASSET_CACHE).then(async (cache) => {
        const cached = await cache.match(request);
        const networkPromise = fetch(request)
          .then((response) => {
            if (response && response.ok) {
              cache.put(request, response.clone());
            }
            return response;
          })
          .catch(() => cached);

        return cached || networkPromise;
      }),
    );
  }
});
