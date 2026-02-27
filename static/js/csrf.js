// CSRF helper: injects X-CSRF-Token for same-origin unsafe requests.
// Token is expected in <meta name="csrf-token" content="...">.
//
// This patch is intentionally small and global, so other modules don't need changes.
(function () {
  try {
    const meta = document.querySelector('meta[name="csrf-token"]');
    const token = meta ? (meta.getAttribute('content') || '') : '';
    if (!token) return;

    window.__CSRF_TOKEN__ = token;

    const isUnsafe = (m) => ['POST', 'PUT', 'PATCH', 'DELETE'].includes(String(m || 'GET').toUpperCase());
    const isSameOriginUrl = (url) => {
      try {
        if (!url) return true;
        if (typeof url !== 'string') return true;
        // relative URL
        if (url.startsWith('/')) return true;
        // same origin absolute URL
        return url.startsWith(window.location.origin);
      } catch (e) { return true; }
    };

    const origFetch = window.fetch.bind(window);

    window.fetch = function (input, init) {
      init = init || {};
      const method = (init.method || (input && input.method) || 'GET');

      // Only patch same-origin unsafe requests
      let url = null;
      if (typeof input === 'string') url = input;
      else if (input && typeof input.url === 'string') url = input.url;

      if (token && isUnsafe(method) && isSameOriginUrl(url)) {
        // If Request object is passed, clone it with extra headers
        if (input instanceof Request) {
          const headers = new Headers(input.headers);
          if (!headers.has('X-CSRF-Token')) headers.set('X-CSRF-Token', token);
          input = new Request(input, { headers });
        } else {
          if (!init.headers) init.headers = {};
          if (init.headers instanceof Headers) {
            if (!init.headers.has('X-CSRF-Token')) init.headers.set('X-CSRF-Token', token);
          } else {
            if (!('X-CSRF-Token' in init.headers)) init.headers['X-CSRF-Token'] = token;
          }
        }
      }
      return origFetch(input, init);
    };
  } catch (e) {
    // no-op
  }
})();
