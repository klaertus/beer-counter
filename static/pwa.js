/* Register the service worker. The SW must be at /static/sw.js.
   Note: for full scope over /s/<code>/* the SW scope defaults to /static/ which
   covers static assets only. Session pages are handled by network-first fallback. */
if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
        navigator.serviceWorker.register('/static/sw.js?v=3')
            .catch(() => { /* SW unavailable — app still works normally */ });
    });
}
