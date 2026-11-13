const CACHE_NAME = 'mytube-v8';
const STATIC_ASSETS = [
  '/',
  '/index.html',
  '/css/style.css',
  '/js/hls.min.js',
  '/js/api.js',
  '/js/player.js',
  '/js/app.js',
  '/manifest.json'
];

self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
      )
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  // Bypass service worker cache for API requests and video streams
  if (url.pathname.startsWith('/api') || url.pathname.includes('/Videos/') || url.pathname.includes('/stream')) {
    return;
  }
  // Cache-first for local thumbnails (immutable once downloaded)
  if (url.pathname.startsWith('/thumbnails/')) {
    e.respondWith(
      caches.match(e.request).then((cached) => {
        if (cached) return cached;
        return fetch(e.request).then((res) => {
          if (res.ok) {
            const copy = res.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(e.request, copy));
          }
          return res;
        });
      })
    );
    return;
  }
  // Network-first with cache fallback for UI assets so updates apply immediately
  e.respondWith(
    fetch(e.request)
      .then((res) => {
        if (res.ok) {
          const copy = res.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(e.request, copy));
        }
        return res;
      })
      .catch(() => caches.match(e.request))
  );
});
