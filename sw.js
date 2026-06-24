// This empty service worker tricks Chrome into allowing a true PWA installation
self.addEventListener('fetch', (event) => {
  // Pass-through without caching anything
});
