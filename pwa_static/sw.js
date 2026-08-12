const CACHE = 'nifty-signal-v4';
const ASSETS = ['/', '/index.html', '/manifest.json'];

self.addEventListener('install', e => {
  // Delete old cache
  e.waitUntil(
    caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
    .then(() => caches.open(CACHE).then(c => c.addAll(ASSETS)))
  );
});

self.addEventListener('activate', e => {
  // Claim all clients so new SW takes effect immediately
  e.waitUntil(clients.claim());
});

self.addEventListener('fetch', e => {
  // Network-first for API + HTML, cache for static
  if (e.request.url.includes('/api/') || e.request.destination === 'document') {
    e.respondWith(
      fetch(e.request).catch(() => caches.match(e.request))
    );
  } else {
    e.respondWith(
      caches.match(e.request).then(r => r || fetch(e.request))
    );
  }
});
