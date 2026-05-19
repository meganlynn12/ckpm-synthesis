const CACHE = 'ckpm-v8';
const STATIC_ASSETS = ['./manifest.json'];

// Never cache index.html — always fetch fresh from network
// Only cache manifest and output JSON (network-first for JSON)

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE).then(c => c.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);

  // index.html — always network, never cache
  if (url.pathname === '/' ||
      url.pathname.endsWith('/index.html') ||
      url.pathname.endsWith('ckpm-synthesis/') ||
      url.pathname.endsWith('ckpm-synthesis')) {
    e.respondWith(fetch(e.request));
    return;
  }

  // Output JSON — network first, fall back to cache
  if (url.pathname.includes('/output/') && url.pathname.endsWith('.json')) {
    e.respondWith(
      fetch(e.request)
        .then(res => {
          const clone = res.clone();
          caches.open(CACHE).then(c => c.put(e.request, clone));
          return res;
        })
        .catch(() => caches.match(e.request))
    );
    return;
  }

  // Everything else — cache first
  e.respondWith(
    caches.match(e.request).then(cached => cached || fetch(e.request))
  );
});