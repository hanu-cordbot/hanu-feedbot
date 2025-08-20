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

    // Fallback: unknown route
    return jsonResponse({ error: 'not_found' }, 404);

  } catch (err) {
    return jsonResponse({ error: 'internal_error', message: String(err) }, 500);
  }
}

function mapPathToKey(pathname) {
  // Map public routes to keys in the R2 bucket
  switch (pathname) {
    case '/api/public/feeds':
      return 'data/feeds.json';
    case '/api/public/meta':
      return 'data/meta.json';
    case '/api/public/stats':
      return 'data/stats.json';
    default:
      return pathname.replace(/^\//, '');
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
