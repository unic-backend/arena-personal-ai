/* Usman service worker: app-shell offline cache, never caches private APIs. */
const CACHE = 'usman-shell-v1';
const PRECACHE = [
  '/',
  '/index.html',
  '/offline.html',
  '/manifest.webmanifest',
  '/icons/usman.svg',
  '/icons/usman-maskable.svg',
  '/icons/usman-512.png',
];

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(PRECACHE)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((key) => key.startsWith('usman-shell-') && key !== CACHE).map((key) => caches.delete(key))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener('message', (event) => {
  if (event.data?.type === 'SKIP_WAITING') self.skipWaiting();
});

self.addEventListener('fetch', (event) => {
  const request = event.request;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);

  // Never intercept a different origin or any backend/API endpoint.
  if (url.origin !== self.location.origin) return;
  if (/\/(api|agent|connectors|files)(\/|$)/.test(url.pathname)) return;

  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response.ok) {
            const copy = response.clone();
            caches.open(CACHE).then((cache) => cache.put('/index.html', copy));
          }
          return response;
        })
        .catch(async () => (await caches.match('/index.html')) || (await caches.match('/offline.html'))),
    );
    return;
  }

  event.respondWith(
    caches.match(request).then((cached) => cached || fetch(request).then((response) => {
      if (response.ok && ['style', 'script', 'font', 'image'].includes(request.destination)) {
        const copy = response.clone();
        caches.open(CACHE).then((cache) => cache.put(request, copy));
      }
      return response;
    })),
  );
});