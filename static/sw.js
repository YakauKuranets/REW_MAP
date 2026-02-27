/*
 * Simple service worker with static asset caching.
 *
 * The service worker pre-caches core static assets on install and
 * serves them from cache when offline. Non‑API requests go through
 * a cache‑first strategy: if an asset is cached, it is returned
 * immediately; otherwise it is fetched from the network and added to
 * the cache for subsequent use. API requests are always passed
 * through to the network to avoid caching potentially stale data.
 */

const CACHE_NAME = 'app-cache-v1';

const ASSETS = [
  '/',
  '/static/css/style.css',
  '/static/js/addresses.js',
  '/static/js/admin_users.js',
  '/static/js/analytics.js',
  '/static/js/chat.js',
  '/static/js/export.js',
  '/static/js/extra.js',
  '/static/js/filters.js',
  '/static/js/main.js',
  '/static/js/map_core.js',
  '/static/js/notify.js',
  '/static/js/offline.js',
  '/static/js/requests.js',
  '/static/js/search.js',
  '/static/js/sidebar.js',
  '/static/js/ui.js',
  '/static/js/zones.js',
  '/static/vendor/leaflet.js',
  '/static/vendor/leaflet.css',
  '/static/vendor/MarkerCluster.js',
  '/static/vendor/MarkerCluster.css',
  '/static/vendor/leaflet.draw.js',
  '/static/vendor/leaflet.draw.css',
  '/static/vendor/fontawesome.css',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(ASSETS);
    })
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys
          .filter((key) => key !== CACHE_NAME)
          .map((key) => caches.delete(key))
      );
    })
  );
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith('/api')) return;
  event.respondWith(
    caches.match(request).then((cached) => {
      if (cached) return cached;
      return fetch(request)
        .then((response) => {
          const respClone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, respClone));
          return response;
        })
        .catch(() => caches.match('/'));
    })
  );
});
