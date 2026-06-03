/* Beer Counter — Service Worker v2
   Strategy:
   - Static assets (/static/*): cache-first
   - API calls (/s/*/api/*): network-only (never cache live data)
   - Everything else: network-first with cache fallback
*/

const CACHE_NAME = 'beer-counter-v3';
const api = {};
const STATIC_ASSETS = [
    '/static/style.css',
    '/static/manifest.json',
    '/static/icons/icon-192x192.png',
    '/static/icons/icon-512x512.png',
];

self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(CACHE_NAME).then(cache => cache.addAll(STATIC_ASSETS))
    );
    self.skipWaiting();
});

self.addEventListener('activate', event => {
    // Remove old cache versions
    event.waitUntil(
        caches.keys().then(keys =>
            Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
        )
    );
    self.clients.claim();
});

self.addEventListener('fetch', event => {
    const url = new URL(event.request.url);

    // Never intercept non-GET requests (POST drinks, form submissions)
    if (event.request.method !== 'GET') return;

    // Never cache API endpoints — always go to network
    if (url.pathname.includes('/api/')) {
        event.respondWith(fetch(event.request));
        return;
    }

    // Cache-first for static assets
    if (url.pathname.startsWith('/static/')) {
        event.respondWith(
            caches.match(event.request).then(cached => cached || fetch(event.request))
        );
        return;
    }

    // Network-first for all other pages
    event.respondWith(
        fetch(event.request).catch(() => caches.match(event.request))
    );
});
