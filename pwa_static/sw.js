// Self-destructing service worker — disabled for now
// To re-enable PWA: revert to previous sw.js and re-register
self.addEventListener('install', e => {
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  // Delete ALL caches
  e.waitUntil(
    caches.keys().then(keys => Promise.all(keys.map(k => caches.delete(k))))
    .then(() => self.registration.unregister())
  );
});

// Pass through all requests
self.addEventListener('fetch', e => {
  e.respondWith(fetch(e.request));
});
