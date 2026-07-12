// Isaac Service Worker - Offline Support & Caching

const CACHE_NAME = 'isaac-v1';
const RUNTIME_CACHE = 'isaac-runtime-v1';

// Assets zum Cachen beim Install
const ASSETS_TO_CACHE = [
    '/',
    '/index.html',
    '/style.css',
    '/app.js'
];

// ============================================
// Install Event - Assets cachen
// ============================================
self.addEventListener('install', (event) => {
    console.log('🔧 Service Worker Installing...');
    
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then((cache) => {
                console.log('📦 Caching assets...');
                return cache.addAll(ASSETS_TO_CACHE);
            })
            .then(() => {
                console.log('✅ Assets cached. Activating...');
                return self.skipWaiting(); // Sofort aktivieren
            })
            .catch((error) => {
                console.error('❌ Cache error:', error);
            })
    );
});

// ============================================
// Activate Event - Alte Caches löschen
// ============================================
self.addEventListener('activate', (event) => {
    console.log('🚀 Service Worker Activating...');
    
    event.waitUntil(
        caches.keys()
            .then((cacheNames) => {
                return Promise.all(
                    cacheNames.map((cacheName) => {
                        if (cacheName !== CACHE_NAME && cacheName !== RUNTIME_CACHE) {
                            console.log('🗑️ Deleting old cache:', cacheName);
                            return caches.delete(cacheName);
                        }
                    })
                );
            })
            .then(() => self.clients.claim()) // Alle Clients sofort kontrollieren
    );
});

// ============================================
// Fetch Event - Network First, Cache Fallback
// ============================================
self.addEventListener('fetch', (event) => {
    const { request } = event;
    const url = new URL(request.url);

    // WebSocket requests nicht intercepten
    if (url.protocol === 'ws:' || url.protocol === 'wss:') {
        return;
    }

    // GET requests nur cachen
    if (request.method !== 'GET') {
        return;
    }

    // ============================================
    // 1. Versuche Netzwerk
    // ============================================
    event.respondWith(
        fetch(request)
            .then((response) => {
                // Erfolgreiche Response cachen
                if (response && response.status === 200) {
                    const responseClone = response.clone();
                    caches.open(RUNTIME_CACHE)
                        .then((cache) => {
                            cache.put(request, responseClone);
                        });
                }
                return response;
            })
            .catch(() => {
                // ============================================
                // 2. Netzwerk fehlgeschlagen - Cache fallback
                // ============================================
                console.log('📴 Network failed, using cache:', request.url);
                
                return caches.match(request)
                    .then((response) => {
                        if (response) {
                            return response;
                        }

                        // ============================================
                        // 3. Auch Cache fehlgeschlagen - Offline page
                        // ============================================
                        if (request.destination === 'document') {
                            return caches.match('/index.html');
                        }

                        // Fallback für andere Requests
                        return new Response('Offline - Asset nicht verfügbar', {
                            status: 503,
                            statusText: 'Service Unavailable',
                            headers: new Headers({
                                'Content-Type': 'text/plain'
                            })
                        });
                    });
            })
    );
});

// ============================================
// Message Handling - Kommunikation mit App
// ============================================
self.addEventListener('message', (event) => {
    const { type, payload } = event.data;

    if (type === 'CLEAR_CACHE') {
        caches.delete(RUNTIME_CACHE)
            .then(() => {
                event.ports[0].postMessage({ success: true });
                console.log('🗑️ Runtime cache cleared');
            });
    }

    if (type === 'GET_CACHE_SIZE') {
        caches.keys().then((names) => {
            let totalSize = 0;
            return Promise.all(
                names.map((name) =>
                    caches.open(name).then((cache) =>
                        cache.keys().then((requests) => {
                            console.log(`Cache "${name}" hat ${requests.length} items`);
                        })
                    )
                )
            ).then(() => {
                event.ports[0].postMessage({ totalSize });
            });
        });
    }

    if (type === 'SKIP_WAITING') {
        self.skipWaiting();
    }
});

// ============================================
// Push Notifications (zukünftig)
// ============================================
self.addEventListener('push', (event) => {
    if (!event.data) return;

    const data = event.data.json();
    const options = {
        body: data.body || 'Isaac hat eine Nachricht für dich',
        icon: '/icon.png',
        badge: '/badge.png',
        tag: 'isaac-notification'
    };

    event.waitUntil(
        self.registration.showNotification(data.title || 'Isaac', options)
    );
});

// Notification Click Handler
self.addEventListener('notificationclick', (event) => {
    event.notification.close();
    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true })
            .then((clientList) => {
                // Finde bereits offenes Fenster
                for (let client of clientList) {
                    if (client.url === '/' && 'focus' in client) {
                        return client.focus();
                    }
                }
                // Oder öffne neues
                if (clients.openWindow) {
                    return clients.openWindow('/');
                }
            })
    );
});

console.log('✅ Isaac Service Worker loaded');
