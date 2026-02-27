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

// Update the cache name to force clients to refresh caches when assets change
const CACHE_NAME = 'app-cache-v1';

// List of static assets to precache. Extend this list as you add new files.
const ASSETS = [
  '/',
  '/static/css/style.css',
  // JavaScript modules
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
  // Vendor libraries (placeholders to be replaced with real files for full offline support)
  '/static/vendor/leaflet.js',
  '/static/vendor/leaflet.css',
  '/static/vendor/MarkerCluster.js',
  '/static/vendor/MarkerCluster.css',
  '/static/vendor/leaflet.draw.js',
  '/static/vendor/leaflet.draw.css',
  '/static/vendor/fontawesome.css',
];

// During the install phase, cache all predefined assets
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(ASSETS);
    })
  );
  // Activate the service worker immediately
  self.skipWaiting();
});

// Clean up old caches during activation
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

// Intercept fetch requests to implement cache‑first strategy for static assets
self.addEventListener('fetch', (event) => {
  const { request } = event;
  // Only handle GET requests from our own origin
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  // Skip API calls – always go to the network for fresh data
  if (url.pathname.startsWith('/api')) return;

  event.respondWith(
    caches.match(request).then((cached) => {
      if (cached) {
        return cached;
      }
      return fetch(request)
        .then((response) => {
          // Put a clone of the response in the cache for future access
          const respClone = response.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(request, respClone);
          });
          return response;
        })
        .catch(() => {
          // If the network is unavailable, serve a fallback if present
          return caches.match('/');
        });
    })
  );
});
