const CACHE_NAME = "promptlibrary-shell-v2";
const SHELL = [
  "/static/app.css", "/static/app.js", "/static/manifest.json",
  "/static/favicon.ico", "/static/favicon-32x32.png", "/static/apple-touch-icon.png",
  "/static/android-chrome-192x192.png", "/static/android-chrome-512x512.png", "/static/app-icon.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET" || new URL(event.request.url).origin !== self.location.origin) return;
  event.respondWith(fetch(event.request).catch(() => caches.match(event.request)));
});
