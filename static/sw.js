const CACHE_NAME = "inventario-qr-v6";
const urlsToCache = [
  "/static/icon-192.png",
  "/static/icon-512.png",
  "/static/apple-touch-icon.png",
];

self.addEventListener("install", (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(urlsToCache))
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
      )
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;

  const url = new URL(req.url);
  // Nunca cachear APIs nem páginas HTML dinâmicas
  if (url.pathname.startsWith("/api/") || url.pathname.endsWith(".json")) {
    event.respondWith(fetch(req));
    return;
  }
  if (
    url.pathname === "/" ||
    url.pathname === "/scanner" ||
    url.pathname === "/contagem" ||
    url.pathname === "/login" ||
    !url.pathname.includes(".")
  ) {
    event.respondWith(
      fetch(req).catch(() => caches.match(req))
    );
    return;
  }

  // Assets estáticos: network-first com fallback cache
  event.respondWith(
    fetch(req)
      .then((response) => {
        if (response && response.status === 200) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(req, clone));
        }
        return response;
      })
      .catch(() => caches.match(req))
  );
});
