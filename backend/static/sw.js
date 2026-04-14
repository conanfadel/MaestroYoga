/* Placeholder service worker: no offline caching. Satisfies clients that request /sw.js (e.g. cached PWA probes). */
self.addEventListener("install", function () {
  self.skipWaiting();
});
self.addEventListener("activate", function (event) {
  event.waitUntil(self.clients.claim());
});
