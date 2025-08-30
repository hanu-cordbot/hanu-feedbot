// R2-backed Cloudflare Worker router
// Assumptions (set in Worker environment):
// - R2 binding named `FEEDS_BUCKET` containing JSON files under keys like 'dashboard/data/stats.json'
// - A secret/environment binding `ADMIN_TOKEN` with a bearer token for admin writes
//
// Data layout:
// - Published/derived data lives under DASH_PREFIX (default: dashboard/data)
// - Authoritative editable sources live under SOURCE_PREFIX (default: dashboard/data/source)
const DASH_PREFIX = (typeof DASHBOARD_PREFIX !== 'undefined' && DASHBOARD_PREFIX) ? DASHBOARD_PREFIX.replace(/^\/+|\/+$/g, '') : 'dashboard/data';
const SOURCE_PREFIX = (typeof SOURCE_PREFIX !== 'undefined' && SOURCE_PREFIX) ? SOURCE_PREFIX.replace(/^\/+|\/+$/g, '') : `${DASH_PREFIX}/source`;

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
    // Simple health endpoint for dashboards
    if (request.method === 'GET' && (pathname === '/health' || pathname === '/api/health')) {
      return jsonResponse({ status: 'ok', service: 'hanu-api-proxy' }, 200);
    }
    // Public read endpoints (serve JSON from R2)
    if (request.method === 'GET' && (pathname === '/api/public/meta' || pathname === '/api/public/stats')) {
      const key = mapPathToKey(pathname);
      const obj = await FEEDS_BUCKET.get(key) || await FEEDS_BUCKET.get(key.replace(DASH_PREFIX, SOURCE_PREFIX));
      if (!obj) return jsonResponse({ error: 'not_found' }, 404);
      const text = await obj.text();
      return new Response(text, { status: 200, headers: jsonCorsHeaders() });
    }

    // Public channels list for display-only UIs
    if (request.method === 'GET' && pathname === '/api/public/channels') {
      const obj = await (FEEDS_BUCKET.get(`${SOURCE_PREFIX}/channels.json`) || FEEDS_BUCKET.get(`${DASH_PREFIX}/channels.json`));
      if (!obj) return jsonResponse({ channels: [] }, 200);
      try {
        const txt = await obj.text();
        const parsed = JSON.parse(txt);
        const channels = Array.isArray(parsed) ? parsed : (Array.isArray(parsed.channels) ? parsed.channels : []);
        return jsonResponse({ channels }, 200);
      } catch (e) {
        return jsonResponse({ channels: [] }, 200);
      }
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

    // Public API: GET /api/public/feeds -> aggregate from stats + source configs
    if (request.method === 'GET' && pathname === '/api/public/feeds') {
      // Load stats from DASH_PREFIX, fallback to legacy
      const statsObj = await (FEEDS_BUCKET.get(`${DASH_PREFIX}/stats.json`) || FEEDS_BUCKET.get('dashboard/data/stats.json') || FEEDS_BUCKET.get('data/stats.json'));
      let statsJson = null;
      if (statsObj) {
        try { statsJson = JSON.parse(await statsObj.text()); } catch (e) { statsJson = null; }
      }

      let feeds = [];
      const metadata = {};
      let lastUpdated = new Date().toISOString();
      let totalFeeds = 0;
      if (statsJson && statsJson.stats && statsJson.stats.feed_health) {
        lastUpdated = statsJson.stats.last_updated || lastUpdated;
        totalFeeds = statsJson.stats.total_feeds || 0;
        for (const feed of Object.values(statsJson.stats.feed_health)) {
          feeds.push({
            url: feed.url,
            title: feed.title || 'Unknown Feed',
            description: feed.description || '',
            entry_count: feed.entry_count || 0,
            last_post: feed.last_post,
            last_updated: feed.last_updated,
            has_metadata: !!feed.has_metadata,
            channel: feed.channel,
            page_url: feed.page_url,
            status: feed.status || 'unknown'
          });
          metadata[feed.url] = {
            title: feed.title || 'Unknown Feed',
            last_post: feed.last_post || null,
            page_url: feed.page_url || null
          };
        }
      }

      // Fallback: if stats are missing, synthesize list from feeds.txt
      if (feeds.length === 0) {
        const feedsTxtObj = await (FEEDS_BUCKET.get(`${SOURCE_PREFIX}/feeds.txt`) || FEEDS_BUCKET.get(`${DASH_PREFIX}/feeds.txt`) || FEEDS_BUCKET.get('feeds.txt'));
        if (feedsTxtObj) {
          try {
            const txt = await feedsTxtObj.text();
            const lines = txt.split(/\r?\n/).map(l => l.trim()).filter(Boolean).filter(l => !l.startsWith('#'));
            feeds = lines.map(u => ({ url: u }));
            totalFeeds = feeds.length;
          } catch (e) {
            // ignore
          }
        }
      }

      // Load mappings (feed_map.json)
      const mapObj = await (FEEDS_BUCKET.get(`${SOURCE_PREFIX}/feed_map.json`) || FEEDS_BUCKET.get(`${DASH_PREFIX}/feed_map.json`) || FEEDS_BUCKET.get('feed_map.json'));
      const mappings = {};
      if (mapObj) {
        try {
          const rawMap = JSON.parse(await mapObj.text());
          for (const [k, v] of Object.entries(rawMap)) {
            if (v && typeof v === 'object') {
              const cid = v.channel || v.channel_id || v.id || v.discord_channel || null;
              if (cid) mappings[k] = String(cid);
            } else if (typeof v === 'string' || typeof v === 'number') {
              mappings[k] = String(v);
            }
          }
        } catch (e) {}
      }

      // Load channels list
      const chObj = await (FEEDS_BUCKET.get(`${SOURCE_PREFIX}/channels.json`) || FEEDS_BUCKET.get(`${DASH_PREFIX}/channels.json`) || FEEDS_BUCKET.get('channels.json'));
      let channels = [];
      if (chObj) {
        try {
          const cj = JSON.parse(await chObj.text());
          if (Array.isArray(cj)) channels = cj; else if (Array.isArray(cj.channels)) channels = cj.channels;
        } catch (e) {}
      }

      // Load groups mapping
      const grpObj = await (FEEDS_BUCKET.get(`${SOURCE_PREFIX}/groups.json`) || FEEDS_BUCKET.get(`${DASH_PREFIX}/groups.json`) || FEEDS_BUCKET.get('groups.json'));
      let groups = {};
      if (grpObj) {
        try { groups = JSON.parse(await grpObj.text()); } catch (e) { groups = {}; }
      }

      return jsonResponse({
        last_updated: lastUpdated,
        total_feeds: totalFeeds || feeds.length,
        feeds,
        metadata,
        mappings,
        groups,
        channels
      }, 200);
    }

    // Admin API: GET /api/feeds (protected) -> list from SOURCE_PREFIX/feeds.txt
    if (request.method === 'GET' && pathname === '/api/feeds') {
      if (!verifyBearer(request)) return jsonResponse({ error: 'Authentication required' }, 401);
      const obj = await FEEDS_BUCKET.get(`${SOURCE_PREFIX}/feeds.txt`) || await FEEDS_BUCKET.get(`${DASH_PREFIX}/feeds.txt`);
      const text = obj ? await obj.text() : '';
      const feeds = text.split(/\r?\n/).map(l => l.trim()).filter(Boolean);
      return jsonResponse({ feeds }, 200);
    }

    // Admin API: POST /api/feeds (protected) -> add feed URL to SOURCE_PREFIX/feeds.txt
    if (request.method === 'POST' && pathname === '/api/feeds') {
      if (!verifyBearer(request)) return jsonResponse({ error: 'Authentication required' }, 401);
      const body = await request.json().catch(() => ({}));
      const feedUrl = (body.feedUrl || body.url || '').toString();
      if (!feedUrl) return jsonResponse({ error: 'feedUrl required' }, 400);
      const obj = await FEEDS_BUCKET.get(`${SOURCE_PREFIX}/feeds.txt`) || await FEEDS_BUCKET.get(`${DASH_PREFIX}/feeds.txt`);
      const current = obj ? (await obj.text()) : '';
      const lines = current.split(/\r?\n/).map(l => l.trim()).filter(Boolean);
      if (!lines.includes(feedUrl)) lines.push(feedUrl);
      const next = lines.join('\n') + '\n';
      await FEEDS_BUCKET.put(`${SOURCE_PREFIX}/feeds.txt`, next, { httpMetadata: { contentType: 'text/plain' } });
      return jsonResponse({ success: true, feed: feedUrl }, 200);
    }

    // Admin API: DELETE /api/feeds (protected) -> remove feed URL
    if (request.method === 'DELETE' && pathname === '/api/feeds') {
      if (!verifyBearer(request)) return jsonResponse({ error: 'Authentication required' }, 401);
      const body = await request.json().catch(() => ({}));
      const feedUrl = (body.feedUrl || body.url || '').toString();
      if (!feedUrl) return jsonResponse({ error: 'feedUrl required' }, 400);
      const obj = await FEEDS_BUCKET.get(`${SOURCE_PREFIX}/feeds.txt`) || await FEEDS_BUCKET.get(`${DASH_PREFIX}/feeds.txt`);
      const current = obj ? (await obj.text()) : '';
      const lines = current.split(/\r?\n/).map(l => l.trim());
      const filtered = lines.filter(l => l && l !== feedUrl).join('\n') + '\n';
      await FEEDS_BUCKET.put(`${SOURCE_PREFIX}/feeds.txt`, filtered, { httpMetadata: { contentType: 'text/plain' } });
      return jsonResponse({ success: true }, 200);
    }

    // Admin API: POST /api/feed-mappings (protected) -> update feed_map.json with channel mappings
    if (request.method === 'POST' && pathname === '/api/feed-mappings') {
      if (!verifyBearer(request)) return jsonResponse({ error: 'Authentication required' }, 401);
      const body = await request.json().catch(() => ({}));
      const feedUrl = (body.feedUrl || body.url || '').toString();
      const channelId = (body.channelId ?? body.channel ?? null);
      const channelIdStr = (channelId == null ? null : String(channelId));
      
      if (!feedUrl) return jsonResponse({ error: 'feedUrl required' }, 400);
      
      try {
        // Load existing feed_map.json (prefer SOURCE_PREFIX, fallback to DASH_PREFIX)
        const obj = await FEEDS_BUCKET.get(`${SOURCE_PREFIX}/feed_map.json`) || await FEEDS_BUCKET.get(`${DASH_PREFIX}/feed_map.json`);
        let feedMap = {};
        if (obj) {
          try {
            feedMap = JSON.parse(await obj.text());
          } catch (e) {
            console.warn('Failed to parse existing feed_map.json:', e);
          }
        }
        
        // Update mapping (simplified format: url -> channelId)
        if (channelIdStr) {
          feedMap[feedUrl] = channelIdStr;
        } else {
          // Remove mapping if no channelId provided
          delete feedMap[feedUrl];
        }
        
        // Save updated feed_map.json
        const contents = JSON.stringify(feedMap, null, 2);
        await FEEDS_BUCKET.put(`${SOURCE_PREFIX}/feed_map.json`, contents, { 
          httpMetadata: { contentType: 'application/json' } 
        });
        
        return jsonResponse({ 
          success: true, 
          feedUrl,
          channelId: channelIdStr,
          message: channelIdStr ? 'Mapping updated' : 'Mapping removed'
        }, 200);
        
      } catch (error) {
        console.error('Failed to update feed mapping:', error);
        return jsonResponse({ 
          error: 'Failed to update mapping', 
          message: error.message 
        }, 500);
      }
    }

    // Admin API: POST /api/feed-groups (protected) -> set group for a feed
    if (request.method === 'POST' && pathname === '/api/feed-groups') {
      if (!verifyBearer(request)) return jsonResponse({ error: 'Authentication required' }, 401);
      const body = await request.json().catch(() => ({}));
      const feedUrl = (body.feedUrl || body.url || '').toString();
      const groupName = (body.groupName || body.group || '').toString();
      if (!feedUrl) return jsonResponse({ error: 'feedUrl required' }, 400);
      const obj = await FEEDS_BUCKET.get(`${SOURCE_PREFIX}/groups.json`) || await FEEDS_BUCKET.get(`${DASH_PREFIX}/groups.json`);
      const groups = obj ? JSON.parse(await obj.text()) : {};
      if (groupName) groups[feedUrl] = groupName; else delete groups[feedUrl];
      await FEEDS_BUCKET.put(`${SOURCE_PREFIX}/groups.json`, JSON.stringify(groups, null, 2), { httpMetadata: { contentType: 'application/json' } });
      return jsonResponse({ success: true, feedUrl, groupName: groupName || null }, 200);
    }

    // Admin API: GET/POST/PUT/DELETE /api/groups (protected)
    if (pathname === '/api/groups') {
      if (!verifyBearer(request)) return jsonResponse({ error: 'Authentication required' }, 401);
      const listKey = `${SOURCE_PREFIX}/group_list.json`;
      const mapKey = `${SOURCE_PREFIX}/groups.json`;
      if (request.method === 'GET') {
        const l = await FEEDS_BUCKET.get(listKey) || await FEEDS_BUCKET.get(`${DASH_PREFIX}/group_list.json`);
        const m = await FEEDS_BUCKET.get(mapKey) || await FEEDS_BUCKET.get(`${DASH_PREFIX}/groups.json`);
        const mapping = m ? JSON.parse(await m.text()) : {};
        const list = l ? JSON.parse(await l.text()) : Array.from(new Set(Object.values(mapping)));
        return jsonResponse({ groups: list, mapping }, 200);
      }
      if (request.method === 'POST') {
        const body = await request.json().catch(() => ({}));
        const name = (body.groupName || body.name || '').toString().trim();
        if (!name) return jsonResponse({ error: 'groupName required' }, 400);
        const l = await FEEDS_BUCKET.get(listKey) || await FEEDS_BUCKET.get(`${DASH_PREFIX}/group_list.json`);
        const list = l ? JSON.parse(await l.text()) : [];
        if (!list.includes(name)) list.push(name);
        await FEEDS_BUCKET.put(listKey, JSON.stringify(list, null, 2));
        return jsonResponse({ success: true, groups: list }, 200);
      }
      if (request.method === 'PUT') {
        const body = await request.json().catch(() => ({}));
        const oldName = (body.oldName || '').toString();
        const newName = (body.newName || '').toString();
        if (!oldName || !newName || oldName === newName) return jsonResponse({ error: 'invalid_names' }, 400);
        const l = await FEEDS_BUCKET.get(listKey) || await FEEDS_BUCKET.get(`${DASH_PREFIX}/group_list.json`);
        const m = await FEEDS_BUCKET.get(mapKey) || await FEEDS_BUCKET.get(`${DASH_PREFIX}/groups.json`);
        const list = l ? JSON.parse(await l.text()) : [];
        const mapping = m ? JSON.parse(await m.text()) : {};
        const renamed = list.map(g => (g === oldName ? newName : g));
        const newMap = {};
        for (const [k, v] of Object.entries(mapping)) newMap[k] = (v === oldName ? newName : v);
        await FEEDS_BUCKET.put(listKey, JSON.stringify(renamed, null, 2));
        await FEEDS_BUCKET.put(mapKey, JSON.stringify(newMap, null, 2));
        return jsonResponse({ success: true, groups: renamed, mapping: newMap }, 200);
      }
      if (request.method === 'DELETE') {
        const name = (url.searchParams.get('name') || '').toString();
        if (!name) return jsonResponse({ error: 'name required' }, 400);
        const l = await FEEDS_BUCKET.get(listKey) || await FEEDS_BUCKET.get(`${DASH_PREFIX}/group_list.json`);
        const m = await FEEDS_BUCKET.get(mapKey) || await FEEDS_BUCKET.get(`${DASH_PREFIX}/groups.json`);
        const list = l ? JSON.parse(await l.text()) : [];
        const mapping = m ? JSON.parse(await m.text()) : {};
        const filtered = list.filter(g => g !== name);
        for (const k of Object.keys(mapping)) if (mapping[k] === name) delete mapping[k];
        await FEEDS_BUCKET.put(listKey, JSON.stringify(filtered, null, 2));
        await FEEDS_BUCKET.put(mapKey, JSON.stringify(mapping, null, 2));
        return jsonResponse({ success: true, groups: filtered, mapping }, 200);
      }
    }

    // Admin API: GET/POST/DELETE /api/channels (protected)
    if (pathname === '/api/channels') {
      if (!verifyBearer(request)) return jsonResponse({ error: 'Authentication required' }, 401);
      const key = `${SOURCE_PREFIX}/channels.json`;
      if (request.method === 'GET') {
        const obj = await FEEDS_BUCKET.get(key) || await FEEDS_BUCKET.get(`${DASH_PREFIX}/channels.json`);
        const channels = obj ? JSON.parse(await obj.text()) : [];
        return jsonResponse({ channels }, 200);
      }
      if (request.method === 'POST') {
        const body = await request.json().catch(() => ({}));
        const id = (body.channelId || body.id || '').toString();
        if (!id) return jsonResponse({ error: 'channelId required' }, 400);
        const obj = await FEEDS_BUCKET.get(key) || await FEEDS_BUCKET.get(`${DASH_PREFIX}/channels.json`);
        const channels = obj ? JSON.parse(await obj.text()) : [];
        const idx = channels.findIndex(ch => String(ch.id) === id);
        const next = { id, name: body.name || '', type: body.type || (body.channelType || 'text') };
        if (idx >= 0) channels[idx] = { ...channels[idx], ...next }; else channels.push(next);
        await FEEDS_BUCKET.put(key, JSON.stringify(channels, null, 2), { httpMetadata: { contentType: 'application/json' } });
        return jsonResponse({ success: true, channel: next }, 200);
      }
      if (request.method === 'DELETE') {
        const body = await request.json().catch(() => ({}));
        const id = (body.channelId || body.id || '').toString();
        if (!id) return jsonResponse({ error: 'channelId required' }, 400);
        const obj = await FEEDS_BUCKET.get(key) || await FEEDS_BUCKET.get(`${DASH_PREFIX}/channels.json`);
        const channels = obj ? JSON.parse(await obj.text()) : [];
        const filtered = channels.filter(ch => String(ch.id) !== id);
        await FEEDS_BUCKET.put(key, JSON.stringify(filtered, null, 2), { httpMetadata: { contentType: 'application/json' } });
        return jsonResponse({ success: true }, 200);
      }
    }

    // Admin API: POST /api/channels/fetch-name (protected)
    if (request.method === 'POST' && pathname === '/api/channels/fetch-name') {
      if (!verifyBearer(request)) return jsonResponse({ error: 'Authentication required' }, 401);
      const body = await request.json().catch(() => ({}));
      const channelId = (body.channelId || body.id || '').toString();
      if (!channelId) return jsonResponse({ error: 'channelId required' }, 400);
      if (typeof DISCORD_BOT_TOKEN === 'undefined' || !DISCORD_BOT_TOKEN) {
        return jsonResponse({ success: false, error: 'DISCORD_BOT_TOKEN not set' }, 500);
      }
      const resp = await fetch(`https://discord.com/api/v10/channels/${channelId}`, {
        headers: { 'Authorization': `Bot ${DISCORD_BOT_TOKEN}` }
      });
      if (!resp.ok) return jsonResponse({ success: false, error: `Discord API ${resp.status}` }, resp.status);
      const info = await resp.json();
      const name = info.name || channelId;
      const type = (function mapDiscordChannelType(t){
        switch (t) {
          case 0: return 'text';
          case 2: return 'voice';
          case 4: return 'category';
          case 5: return 'announcement';
          case 13: return 'stage';
          case 15: return 'forum';
          case 10: case 11: case 12: return 'thread';
          default: return 'text';
        }
      })(info.type);
      const key = `${SOURCE_PREFIX}/channels.json`;
      const obj = await FEEDS_BUCKET.get(key) || await FEEDS_BUCKET.get(`${DASH_PREFIX}/channels.json`);
      const channels = obj ? JSON.parse(await obj.text()) : [];
      const idx = channels.findIndex(ch => String(ch.id) === channelId);
      const next = { id: channelId, name, type };
      if (idx >= 0) channels[idx] = { ...channels[idx], ...next }; else channels.push(next);
      await FEEDS_BUCKET.put(key, JSON.stringify(channels, null, 2), { httpMetadata: { contentType: 'application/json' } });
      return jsonResponse({ success: true, channel: next }, 200);
    }
    // Examples: GET /feed_map.json -> dashboard/data/feed_map.json
    if (request.method === 'GET') {
      const key = mapPathToKey(pathname);
      const obj = await FEEDS_BUCKET.get(key) || await FEEDS_BUCKET.get(key.replace(DASH_PREFIX, SOURCE_PREFIX));
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

function verifyBearer(request) {
  try {
    const auth = request.headers.get('Authorization') || '';
    if (!auth.startsWith('Bearer ')) return false;
    const token = auth.slice('Bearer '.length).trim();
    if (typeof ADMIN_TOKEN !== 'undefined' && ADMIN_TOKEN && token === ADMIN_TOKEN) return true;
    const decoded = JSON.parse(atob(token));
    if (decoded && decoded.exp && decoded.exp > Math.floor(Date.now() / 1000)) return true;
    return false;
  } catch (e) {
    return false;
  }
}

function mapPathToKey(pathname) {
  // Map public routes to keys in the R2 bucket
  // Allow configurable prefix via DASHBOARD_PREFIX binding or default to 'dashboard/data'
  const prefix = DASH_PREFIX; // already normalized
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
