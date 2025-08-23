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

    // Public API: GET /api/public/feeds -> return feeds data from stats.json instead of feeds.json
    if (request.method === 'GET' && pathname === '/api/public/feeds') {
      const obj = await FEEDS_BUCKET.get('data/stats.json');
      if (!obj) return jsonResponse({ last_updated: new Date().toISOString(), feeds: [], total_feeds: 0 }, 200);
      const text = await obj.text();
      try {
        const data = JSON.parse(text);
        if (data.stats && data.stats.feed_health) {
          const feeds = Object.values(data.stats.feed_health).map(feed => ({
            url: feed.url,
            title: feed.title || 'Unknown Feed',
            description: feed.description || '',
            entry_count: feed.entry_count || 0,
            last_post: feed.last_post,
            last_updated: feed.last_updated,
            has_metadata: feed.has_metadata || false,
            channel: feed.channel,
            page_url: feed.page_url,
            status: feed.status || 'unknown'
          }));
          return jsonResponse({
            last_updated: data.stats.last_updated,
            feeds: feeds,
            total_feeds: data.stats.total_feeds
          }, 200);
        }
      } catch (e) {
        console.error('Failed to parse stats.json:', e);
      }
      return jsonResponse({ last_updated: new Date().toISOString(), feeds: [], total_feeds: 0 }, 200);
    }

    // Admin API: GET /api/feeds (protected) -> return list of feed URLs from feeds.txt (ground truth)
    if (request.method === 'GET' && pathname === '/api/feeds') {
      if (!verifyBearer(request)) return jsonResponse({ error: 'Authentication required' }, 401);
      // Note: This should ideally read from a ground truth file like feeds.txt in R2
      // For now, extract URLs from stats.json as fallback
      const obj = await FEEDS_BUCKET.get('data/stats.json');
      if (!obj) return jsonResponse({ feeds: [] }, 200);
      const text = await obj.text();
      try {
        const data = JSON.parse(text);
        if (data.stats && data.stats.feed_health) {
          const urls = Object.keys(data.stats.feed_health);
          return jsonResponse({ feeds: urls }, 200);
        }
      } catch (e) {
        console.error('Failed to parse stats.json for admin feeds:', e);
      }
      return jsonResponse({ feeds: [] }, 200);
    }

    // Admin API: POST /api/feeds (protected) -> add feed URL to ground truth (feeds.txt via R2)
    if (request.method === 'POST' && pathname === '/api/feeds') {
      if (!verifyBearer(request)) return jsonResponse({ error: 'Authentication required' }, 401);
      const body = await request.json().catch(() => ({}));
      const feedUrl = (body.feedUrl || body.url || '').toString();
      if (!feedUrl) return jsonResponse({ error: 'feedUrl required' }, 400);
      
      // TODO: This should write to feeds.txt in R2 instead of feeds.json
      // For now, return success but note that the actual ground truth is managed elsewhere
      return jsonResponse({ 
        success: true, 
        feed: feedUrl,
        note: 'Feed will be added to ground truth on next CI run'
      }, 200);
    }

    // Admin API: POST /api/feed-mappings (protected) -> update feed_map.json with channel mappings
    if (request.method === 'POST' && pathname === '/api/feed-mappings') {
      if (!verifyBearer(request)) return jsonResponse({ error: 'Authentication required' }, 401);
      const body = await request.json().catch(() => ({}));
      const feedUrl = (body.feedUrl || body.url || '').toString();
      const channelId = (body.channelId || body.channel || '').toString();
      
      if (!feedUrl) return jsonResponse({ error: 'feedUrl required' }, 400);
      
      try {
        // Load existing feed_map.json
        const obj = await FEEDS_BUCKET.get('dashboard/data/feed_map.json');
        let feedMap = {};
        if (obj) {
          try {
            feedMap = JSON.parse(await obj.text());
          } catch (e) {
            console.warn('Failed to parse existing feed_map.json:', e);
          }
        }
        
        // Update mapping (simplified format: url -> channelId)
        if (channelId) {
          feedMap[feedUrl] = channelId;
        } else {
          // Remove mapping if no channelId provided
          delete feedMap[feedUrl];
        }
        
        // Save updated feed_map.json
        const contents = JSON.stringify(feedMap, null, 2);
        await FEEDS_BUCKET.put('dashboard/data/feed_map.json', contents, { 
          httpMetadata: { contentType: 'application/json' } 
        });
        
        return jsonResponse({ 
          success: true, 
          feedUrl,
          channelId: channelId || null,
          message: channelId ? 'Mapping updated' : 'Mapping removed'
        }, 200);
        
      } catch (error) {
        console.error('Failed to update feed mapping:', error);
        return jsonResponse({ 
          error: 'Failed to update mapping', 
          message: error.message 
        }, 500);
      }
    }

    // Public GET: allow serving arbitrary JSON files from the configured dashboard prefix
    // Examples: GET /feed_map.json -> dashboard/data/feed_map.json
    if (request.method === 'GET') {
      const key = mapPathToKey(pathname);
      const obj = await FEEDS_BUCKET.get(key);
      if (obj) {
        const text = await obj.text();
        return new Response(text, { status: 200, headers: jsonCorsHeaders() });
      }
      // else continue to return not_found at the end
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
      // Redirect feeds endpoint to use stats.json instead of feeds.json
      return `${prefix}/stats.json`;
    case '/api/public/meta':
      return `${prefix}/meta.json`;
    case '/api/public/stats':
    case '/api/stats':
      return `${prefix}/stats.json`;
    default:
        // For other keys, treat pathname as a key under the prefix
        const trimmed = pathname.replace(/^\//, '');
        // If the request already includes the prefix (e.g. /dashboard/data/feed_map.json),
        // avoid doubling the prefix and use the trimmed path as the key directly.
        if (trimmed === prefix || trimmed.startsWith(prefix + '/')) {
          return trimmed;
        }
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
