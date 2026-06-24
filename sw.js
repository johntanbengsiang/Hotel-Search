self.addEventListener('fetch', (event) => {
  // Satisfies Chrome's requirement for a functional fetch handler
  event.respondWith(fetch(event.request));
});
