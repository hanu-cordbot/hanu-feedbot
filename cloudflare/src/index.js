// R2-backed Cloudflare Worker router
// Assumptions (set in Worker environment):
// - R2 binding named `FEEDS_BUCKET` containing JSON files under keys like 'data/feeds.json'
// - A secret/environment binding `ADMIN_TOKEN` with a bearer token for admin writes

addEventListener('fetch', event => {
  event.respondWith(handleRequest(event));
});

async function handleRequest(event) {
  const { request } = event;
  const url = new URL(request.url);
  const pathname = url.pathname.replace(/\/+$/, ''); // trim trailing slash

  // CORS preflight
  if (request.method === 'OPTIONS') {
    return new Response(null, {
      status: 204,
      headers: corsHeaders()
    });
  }

  try {
    // Public read endpoints (serve JSON from R2)
    if (request.method === 'GET' && (pathname === '/api/public/feeds' || pathname === '/api/public/meta' || pathname === '/api/public/stats')) {
      const key = mapPathToKey(pathname);
      const obj = await FEEDS_BUCKET.get(key);
      if (!obj) return jsonResponse({ error: 'not_found' }, 404);
      const text = await obj.text();
      return new Response(text, { status: 200, headers: jsonCorsHeaders() });
    }

    // Admin upload endpoint: write JSON to R2. Requires Authorization: Bearer <ADMIN_TOKEN>
    if (request.method === 'POST' && pathname === '/api/admin/upload') {
      const auth = request.headers.get('Authorization') || '';
      if (!auth.startsWith('Bearer ')) return jsonResponse({ error: 'unauthorized' }, 401);
      const token = auth.slice('Bearer '.length).trim();
      if (!ADMIN_TOKEN || token !== ADMIN_TOKEN) return jsonResponse({ error: 'forbidden' }, 403);

      const body = await request.json().catch(() => null);
      if (!body || !body.key || !('contents' in body)) return jsonResponse({ error: 'bad_request' }, 400);

      const key = body.key.replace(/^\/+/, '');
      const contents = typeof body.contents === 'string' ? body.contents : JSON.stringify(body.contents);

      await FEEDS_BUCKET.put(key, contents, { httpMetadata: { contentType: 'application/json' } });
      return jsonResponse({ ok: true, key }, 200);
    }

    // Authentication: POST /api/auth/login -> validate ADMIN_USER/ADMIN_PASS and return token
    if (request.method === 'POST' && pathname === '/api/auth/login') {
      const body = await request.json().catch(() => ({}));
      const username = (body.username || '').toString();
      const password = (body.password || '').toString();
      const ADMIN_USER = ADMIN_USER_BINDING || 'admin';
      const ADMIN_PASS = ADMIN_PASS_BINDING || '';
      if (username === ADMIN_USER && password === ADMIN_PASS) {
        const now = Math.floor(Date.now() / 1000);
        const tokenData = { user: username, exp: now + 3600 };
        const token = btoa(JSON.stringify(tokenData));
        return jsonResponse({ success: true, token }, 200);
      }
      return jsonResponse({ success: false, error: 'Invalid credentials' }, 401);
    }

    // Token verification endpoint used by dashboard: GET /api/status
    if (request.method === 'GET' && pathname === '/api/status') {
      const auth = request.headers.get('Authorization') || '';
      if (!auth.startsWith('Bearer ')) return jsonResponse({ error: 'Authentication required' }, 401);
      const token = auth.slice('Bearer '.length).trim();
      try {
        const decoded = JSON.parse(atob(token));
        if (decoded.exp && decoded.exp > Math.floor(Date.now() / 1000)) {
          return jsonResponse({ status: 'ok' }, 200);
        }
      } catch (e) {}
      return jsonResponse({ error: 'Authentication required' }, 401);
    }

    // Admin API: GET /api/feeds (protected) -> return list of feed URLs
    if (request.method === 'GET' && pathname === '/api/feeds') {
      if (!verifyBearer(request)) return jsonResponse({ error: 'Authentication required' }, 401);
      const obj = await FEEDS_BUCKET.get('data/feeds.json');
      if (!obj) return jsonResponse({ feeds: [] }, 200);
      const text = await obj.text();
      try {
        const data = JSON.parse(text);
        // Support both array of strings and new format with objects
        if (Array.isArray(data)) return jsonResponse({ feeds: data }, 200);
        if (data.feeds && Array.isArray(data.feeds)) {
          const urls = data.feeds.map(f => (typeof f === 'string' ? f : f.url)).filter(Boolean);
          return jsonResponse({ feeds: urls }, 200);
        }
        return jsonResponse({ feeds: [] }, 200);
      } catch (e) {
        return jsonResponse({ feeds: [] }, 200);
      }
    }

    // Admin API: POST /api/feeds (protected) -> add feed URL to feeds.json
    if (request.method === 'POST' && pathname === '/api/feeds') {
      if (!verifyBearer(request)) return jsonResponse({ error: 'Authentication required' }, 401);
      const body = await request.json().catch(() => ({}));
      const feedUrl = (body.feedUrl || body.url || '').toString();
      if (!feedUrl) return jsonResponse({ error: 'feedUrl required' }, 400);
      // Read existing
      const obj = await FEEDS_BUCKET.get('data/feeds.json');
      let feedsArr = [];
      if (obj) {
        try { const existing = JSON.parse(await obj.text()); if (existing.feeds) feedsArr = existing.feeds; else if (Array.isArray(existing)) feedsArr = existing; } catch(e){}
      }
      // Normalize entries as objects with url
      const exists = feedsArr.some(f => (typeof f === 'string' ? f : f.url) === feedUrl);
      if (!exists) feedsArr.push({ url: feedUrl });
      const contents = JSON.stringify({ last_updated: new Date().toISOString(), feeds: feedsArr });
      await FEEDS_BUCKET.put('data/feeds.json', contents, { httpMetadata: { contentType: 'application/json' } });
      return jsonResponse({ success: true, feed: feedUrl }, 200);
    }

    // Fallback: route not handled
    return jsonResponse({ error: 'not_found' }, 404);

  } catch (err) {
    return jsonResponse({ error: 'internal_error', message: String(err) }, 500);
  }
}

function mapPathToKey(pathname) {
  // Map public routes to keys in the R2 bucket
  // Allow configurable prefix via DASHBOARD_PREFIX binding or default to 'dashboard/data'
  const rawPrefix = typeof DASHBOARD_PREFIX !== 'undefined' ? DASHBOARD_PREFIX : 'dashboard/data';
  const prefix = rawPrefix.replace(/^\/+|\/+$/g, ''); // trim slashes
  switch (pathname) {
    case '/api/public/feeds':
      return `${prefix}/feeds.json`;
    case '/api/public/meta':
      return `${prefix}/meta.json`;
    case '/api/public/stats':
      return `${prefix}/stats.json`;
    default:
      // For other keys, treat pathname as a key under the prefix
      const trimmed = pathname.replace(/^\//, '');
      return `${prefix}/${trimmed}`;
  }
}

function corsHeaders() {
  return {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET,HEAD,POST,PUT,DELETE,OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, Authorization'
  };
}

function jsonCorsHeaders() {
  const h = new Headers();
  h.set('Content-Type', 'application/json');
  Object.entries(corsHeaders()).forEach(([k, v]) => h.set(k, v));
  return h;
}

function jsonResponse(obj, status = 200) {
  return new Response(JSON.stringify(obj), { status, headers: jsonCorsHeaders() });
}
