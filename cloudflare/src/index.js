

// (top-level export removed; see bottom export default)
// Cloudflare Worker (module) to serve dashboard JSON from R2 with CORS

// ---- Helpers ----
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
  const c = corsHeaders();
  for (const k of Object.keys(c)) h.set(k, c[k]);
  return h;
}
function jsonResponse(obj, status = 200) {
  return new Response(JSON.stringify(obj), { status, headers: jsonCorsHeaders() });
}

function dashPrefix() {
  const raw = (typeof globalThis.DASHBOARD_PREFIX !== 'undefined' && globalThis.DASHBOARD_PREFIX) ? globalThis.DASHBOARD_PREFIX : 'dashboard/data';
  return raw.replace(/^\/+|\/+$/g, '');
}
function sourcePrefix() {
  const raw = (typeof globalThis.SOURCE_PREFIX !== 'undefined' && globalThis.SOURCE_PREFIX) ? globalThis.SOURCE_PREFIX : `${dashPrefix()}/source`;
  return raw.replace(/^\/+|\/+$/g, '');
}

async function getText(key) {
  const obj = await globalThis.FEEDS_BUCKET.get(key);
  return obj ? await obj.text() : null;
}
async function getJson(key) {
  const txt = await getText(key);
  if (!txt) return null;
  try { return JSON.parse(txt); } catch { return null; }
}

// Convert any group mapping to canonical { groupName: [feedUrl, ...] }
function toCanonicalGroupMap(obj) {
  if (!obj || typeof obj !== 'object') return {};
  // If values are arrays, assume already canonical
  let isCanonical = true;
  for (const v of Object.values(obj)) { if (!Array.isArray(v)) { isCanonical = false; break; } }
  if (isCanonical) return obj;
  // Otherwise treat as feed->group and invert
  const out = {};
  for (const [feed, grp] of Object.entries(obj)) {
    if (!grp) continue;
    const g = String(grp);
    if (!out[g]) out[g] = [];
    out[g].push(feed);
  }
  return out;
}

async function handlePublicFeeds() {
  // Try stats first
  const stats = await getJson(`${dashPrefix()}/stats.json`);
  let feeds = [];
  const metadata = {};
  let lastUpdated = new Date().toISOString();
  let totalFeeds = 0;

  if (stats && stats.stats && stats.stats.feed_health) {
    lastUpdated = stats.stats.last_updated || lastUpdated;
    totalFeeds = stats.stats.total_feeds || 0;
    for (const fh of Object.values(stats.stats.feed_health)) {
      feeds.push({
        url: fh.url,
        title: fh.title || 'Unknown Feed',
        description: fh.description || '',
        entry_count: fh.entry_count || 0,
        last_post: fh.last_post,
        last_updated: fh.last_updated,
        has_metadata: !!fh.has_metadata,
        channel: fh.channel,
        page_url: fh.page_url,
        status: fh.status || 'unknown'
      });
      metadata[fh.url] = {
        title: fh.title || 'Unknown Feed',
        last_post: fh.last_post || null,
        page_url: fh.page_url || null
      };
    }
  }

  // Fallback to feeds.txt if stats empty
  if (feeds.length === 0) {
    const txt = await getText(`${sourcePrefix()}/feeds.txt`) || await getText(`${dashPrefix()}/feeds.txt`) || await getText('feeds.txt');
    if (txt) {
      const lines = txt.split(/\r?\n/).map(s => s.trim()).filter(Boolean).filter(s => !s.startsWith('#'));
      feeds = lines.map(url => ({ url }));
      totalFeeds = feeds.length;
    }
  }

  // Load mappings, channels, groups (best-effort)
  const mappings = {};
  const mapJson = await getJson(`${sourcePrefix()}/feed_map.json`) || await getJson(`${dashPrefix()}/feed_map.json`) || {};
  for (const [k, v] of Object.entries(mapJson || {})) {
    if (v && typeof v === 'object') {
      const cid = v.channel || v.channel_id || v.id || v.discord_channel || null;
      if (cid) mappings[k] = String(cid);
    } else if (typeof v === 'string' || typeof v === 'number') {
      mappings[k] = String(v);
    }
  }

  let channels = [];
  const ch = await getJson(`${sourcePrefix()}/channels.json`) || await getJson(`${dashPrefix()}/channels.json`) || [];
  if (Array.isArray(ch)) channels = ch; else if (Array.isArray(ch.channels)) channels = ch.channels;

  // Merge channels from meta.json if available (helps when generator wrote richer data)
  try {
    const meta = await getJson(`${dashPrefix()}/meta.json`);
    const metaChannels = (meta && (Array.isArray(meta.channels) ? meta.channels : (Array.isArray(meta.channels?.channels) ? meta.channels.channels : []))) || [];
    if (metaChannels && metaChannels.length) {
      const byId = new Map((channels || []).map(c => [String(c.id), c]));
      for (const c of metaChannels) {
        const id = c && c.id != null ? String(c.id) : null;
        if (!id) continue;
        const cur = byId.get(id) || {};
        byId.set(id, { id, ...(cur || {}), ...(c || {}) });
      }
      channels = Array.from(byId.values());
    }
  } catch (_) {}

  const groupsRaw = (await getJson(`${sourcePrefix()}/groups.json`)) || (await getJson(`${dashPrefix()}/groups.json`)) || {};
  const groups = toCanonicalGroupMap(groupsRaw);

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

async function handleRequest({ request }) {
  const url = new URL(request.url);
  const pathname = url.pathname.replace(/\/+$/, '');

  if (request.method === 'OPTIONS') {
    return new Response(null, { status: 204, headers: corsHeaders() });
  }

  if (request.method === 'GET' && (pathname === '/health' || pathname === '/api/health')) {
    return jsonResponse({ status: 'ok' }, 200);
  }

  // ---- Auth endpoints ----
  if (request.method === 'POST' && pathname === '/api/auth/login') {
    try {
      const body = await request.json().catch(() => ({}));
      const user = (body.username || '').toString();
      const pass = (body.password || '').toString();
      const U = (globalThis.ADMIN_USER_BINDING || globalThis.ADMIN_USER || 'admin');
      const P = (globalThis.ADMIN_PASS_BINDING || globalThis.ADMIN_PASS || '');
      const ALT = (globalThis.ADMIN_TOKEN || globalThis.GH_BOT_PAT || '');
      // Accept either ADMIN_PASS (preferred), or alternate ADMIN_TOKEN / GH_BOT_PAT as password for convenience
      if ((pass && (pass === P || pass === ALT)) && (!U || user === U || user === 'admin')) {
        const now = Math.floor(Date.now() / 1000);
        const token = btoa(JSON.stringify({ user, exp: now + 3600 }));
        return jsonResponse({ success: true, token }, 200);
      }
      return jsonResponse({ success: false, error: 'invalid_credentials' }, 401);
    } catch (e) {
      return jsonResponse({ success: false, error: 'internal_error' }, 500);
    }
  }
  if (request.method === 'GET' && pathname === '/api/status') {
    const auth = request.headers.get('Authorization') || '';
    if (!auth.startsWith('Bearer ')) return jsonResponse({ error: 'Authentication required' }, 401);
    const token = auth.slice('Bearer '.length).trim();
    try {
      if (typeof globalThis.ADMIN_TOKEN !== 'undefined' && globalThis.ADMIN_TOKEN && token === globalThis.ADMIN_TOKEN) {
        return jsonResponse({ status: 'ok' }, 200);
      }
      const decoded = JSON.parse(atob(token));
      if (decoded.exp && decoded.exp > Math.floor(Date.now() / 1000)) return jsonResponse({ status: 'ok' }, 200);
    } catch (_) {}
    return jsonResponse({ error: 'Authentication required' }, 401);
  }

  if (request.method === 'GET' && pathname === '/api/public/feeds') {
    return await handlePublicFeeds();
  }

  if (request.method === 'GET' && pathname === '/api/public/meta') {
    const meta = await getText(`${dashPrefix()}/meta.json`);
    if (!meta) return jsonResponse({ error: 'not_found' }, 404);
    return new Response(meta, { status: 200, headers: jsonCorsHeaders() });
  }
  if (request.method === 'GET' && (pathname === '/api/public/stats' || pathname === '/api/stats')) {
    const stats = await getText(`${dashPrefix()}/stats.json`);
    if (!stats) return jsonResponse({ error: 'not_found' }, 404);
    return new Response(stats, { status: 200, headers: jsonCorsHeaders() });
  }

  // Public: channels list (no auth)
  if (request.method === 'GET' && pathname === '/api/public/channels') {
    let ch = await getJson(`${sourcePrefix()}/channels.json`) || await getJson(`${dashPrefix()}/channels.json`) || [];
    let arr = Array.isArray(ch) ? ch : (Array.isArray(ch.channels) ? ch.channels : []);
    // Merge from meta.json if richer data available
    try {
      const meta = await getJson(`${dashPrefix()}/meta.json`);
      const metaArr = (meta && (Array.isArray(meta.channels) ? meta.channels : (Array.isArray(meta.channels?.channels) ? meta.channels.channels : []))) || [];
      if (metaArr && metaArr.length) {
        const byId = new Map((arr || []).map(c => [String(c.id), c]));
        for (const c of metaArr) {
          const id = c && c.id != null ? String(c.id) : null;
          if (!id) continue;
          const cur = byId.get(id) || {};
          byId.set(id, { id, ...(cur || {}), ...(c || {}) });
        }
        arr = Array.from(byId.values());
      }
    } catch (_) {}
    // Opportunistic enrichment for records missing name/type (if token available)
    try {
      if (globalThis.DISCORD_BOT_TOKEN && Array.isArray(arr)) {
        const missing = arr.filter(c => !c || !c.id || !c.name || !c.type).slice(0, 20);
        for (const c of missing) {
          const id = String(c.id);
          try {
            const resp = await fetch(`https://discord.com/api/v10/channels/${id}`, { headers: { 'Authorization': `Bot ${globalThis.DISCORD_BOT_TOKEN}` } });
            if (resp.ok) {
              const j = await resp.json();
              const mapType = (t) => {
                switch (t) { case 0: return 'text'; case 2: return 'voice'; case 4: return 'category'; case 5: return 'announcement'; case 13: return 'stage'; case 15: return 'forum'; default: return 'text'; }
              };
              c.name = c.name || j.name || `channel-${id.slice(-4)}`;
              c.type = c.type || mapType(j.type);
            }
          } catch (_) {}
        }
        // Persist back to source for caching if we enriched any
        if (missing.length) {
          try {
            const byId = new Map(arr.map(x => [String(x.id), x]));
            await globalThis.FEEDS_BUCKET.put(`${sourcePrefix()}/channels.json`, JSON.stringify(Array.from(byId.values()), null, 2), { httpMetadata: { contentType: 'application/json' } });
          } catch (_) {}
        }
      }
    } catch (_) {}
    return jsonResponse({ channels: arr }, 200);
  }

  // ---- System health (public) ----
  if (request.method === 'GET' && pathname === '/api/system-health') {
    const out = { status: 'ok', metrics: {}, checks: {} };
    // Load stats.json
    let s = null;
    try { s = await getJson(`${dashPrefix()}/stats.json`); } catch (_) {}
    const stats = s && s.stats ? s.stats : null;
    const now = Date.now();
    const dayMs = 24 * 60 * 60 * 1000;
    const recentLimit = 14 * dayMs;

    // Compute metrics
    let feedHealth = stats && stats.feed_health ? stats.feed_health : {};
    if (feedHealth && typeof feedHealth === 'object') {
      let feedsTotal = 0, mapped = 0, active = 0, stale = 0;
      for (const fh of Object.values(feedHealth)) {
        if (!fh || typeof fh !== 'object') continue;
        feedsTotal++;
        const lp = fh.last_post ? new Date(fh.last_post).getTime() : 0;
        const hasRecent = lp && (now - lp) <= recentLimit;
        const hasChannel = !!(fh.channel && fh.channel.id);
        if (hasChannel) mapped++;
        if (hasRecent) active++; else stale++;
      }
      out.metrics = { feedsTotal, mapped, active, stale, last_updated: stats.last_updated || null };
      // Checks
      out.checks.stats = true;
      out.checks.last_updated_recent = !!(stats && stats.last_updated && (now - new Date(stats.last_updated).getTime()) <= dayMs);
      out.checks.activity_ok = active > 0;
    } else {
      out.checks.stats = false;
    }

    // Presence checks for config files
    const keys = [ `${sourcePrefix()}/feed_map.json`, `${sourcePrefix()}/channels.json`, `${sourcePrefix()}/groups.json`, `${dashPrefix()}/stats.json` ];
    for (const k of keys) {
      try { out.checks[k] = !!(await getText(k)); } catch (_) { out.checks[k] = false; }
    }

    // Status derivation
    if (!out.checks.stats || !out.checks.last_updated_recent) out.status = 'degraded';
    if (out.metrics && out.metrics.feedsTotal > 0 && out.metrics.active === 0) out.status = 'degraded';

    return jsonResponse(out, 200);
  }

  // ---- Admin: helper for bearer verification ----
  function isAuthorized() {
    const auth = request.headers.get('Authorization') || '';
    if (!auth.startsWith('Bearer ')) return false;
    const token = auth.slice('Bearer '.length).trim();
    try {
      if (typeof globalThis.ADMIN_TOKEN !== 'undefined' && globalThis.ADMIN_TOKEN && token === globalThis.ADMIN_TOKEN) return true;
      const decoded = JSON.parse(atob(token));
      return !!(decoded && decoded.exp && decoded.exp > Math.floor(Date.now() / 1000));
    } catch (_) {
      return false;
    }
  }

  // ---- Admin: trigger CI run (GitHub Actions) ----
  if (request.method === 'POST' && pathname === '/api/run-job') {
    if (!isAuthorized()) return jsonResponse({ error: 'Authentication required' }, 401);
    const body = await request.json().catch(() => ({}));
    const ignoreSeen = !!(body && (body.ignoreSeen || body.ignore_seen));
    const repo = (typeof globalThis.GITHUB_REPO !== 'undefined' && globalThis.GITHUB_REPO) ? globalThis.GITHUB_REPO : 'hanu-cordbot/hanu-feedbot';
    const token = (globalThis.GITHUB_PAT || globalThis.GITHUB_TOKEN || globalThis.GH_BOT_PAT || globalThis.GH_BOT_TOKEN || null);
    if (!token) return jsonResponse({ error: 'github_token_missing' }, 500);
    try {
      const resp = await fetch(`https://api.github.com/repos/${repo}/actions/workflows/feed-bot.yml/dispatches`, {
        method: 'POST',
        headers: {
          'Accept': 'application/vnd.github+json',
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          ref: 'main',
          inputs: {
            force_run: 'true',
            debug_mode: 'false',
            max_age_hours: '36',
            ignore_seen: ignoreSeen ? 'true' : 'false'
          }
        })
      });
      if (!resp.ok) {
        const t = await resp.text().catch(() => '');
        return jsonResponse({ error: 'github_dispatch_failed', status: resp.status, body: t }, 502);
      }
      return jsonResponse({ success: true }, 200);
    } catch (e) {
      return jsonResponse({ error: 'github_error', message: String(e) }, 500);
    }
  }

  // ---- Admin: feeds.txt management ----
  if (pathname === '/api/feeds') {
    if (!isAuthorized()) return jsonResponse({ error: 'Authentication required' }, 401);
    if (request.method === 'GET') {
      const txt = await getText(`${sourcePrefix()}/feeds.txt`) || await getText(`${dashPrefix()}/feeds.txt`) || '';
      const feeds = (txt ? txt.split(/\r?\n/) : []).map(s => s.trim()).filter(Boolean);
      return jsonResponse({ feeds }, 200);
    }
    if (request.method === 'POST') {
      const body = await request.json().catch(() => ({}));
      const feedUrl = (body.feedUrl || body.url || '').toString().trim();
      if (!feedUrl) return jsonResponse({ error: 'feedUrl required' }, 400);
      const txt = (await getText(`${sourcePrefix()}/feeds.txt`)) || '';
      const lines = txt.split(/\r?\n/).map(s => s.trim()).filter(Boolean);
      if (!lines.includes(feedUrl)) lines.push(feedUrl);
      await globalThis.FEEDS_BUCKET.put(`${sourcePrefix()}/feeds.txt`, lines.join('\n') + '\n', { httpMetadata: { contentType: 'text/plain' } });
      return jsonResponse({ success: true }, 200);
    }
    if (request.method === 'DELETE') {
      const body = await request.json().catch(() => ({}));
      const feedUrl = (body.feedUrl || body.url || '').toString().trim();
      if (!feedUrl) return jsonResponse({ error: 'feedUrl required' }, 400);
      const txt = (await getText(`${sourcePrefix()}/feeds.txt`)) || '';
      const lines = txt.split(/\r?\n/).map(s => s.trim());
      const filtered = lines.filter(l => l && l !== feedUrl);
      await globalThis.FEEDS_BUCKET.put(`${sourcePrefix()}/feeds.txt`, (filtered.join('\n') + (filtered.length ? '\n' : '')), { httpMetadata: { contentType: 'text/plain' } });
      return jsonResponse({ success: true }, 200);
    }
  }

  // ---- Admin: channels.json management ----
  if (pathname === '/api/channels') {
    if (!isAuthorized()) return jsonResponse({ error: 'Authentication required' }, 401);
    const key = `${sourcePrefix()}/channels.json`;
    if (request.method === 'GET') {
      const ch = await getJson(key) || [];
      const channels = Array.isArray(ch) ? ch : (Array.isArray(ch.channels) ? ch.channels : []);
      return jsonResponse({ channels }, 200);
    }
    if (request.method === 'POST') {
      const body = await request.json().catch(() => ({}));
      const id = (body.channelId || body.id || '').toString().trim();
      let name = (body.channelName || body.name || '').toString();
      let type = (body.channelType || body.type || '').toString();
      if (!id) return jsonResponse({ error: 'channelId required' }, 400);
      // Auto-enrich from Discord when possible
      if ((!name || !type) && globalThis.DISCORD_BOT_TOKEN) {
        try {
          const resp = await fetch(`https://discord.com/api/v10/channels/${id}`, {
            headers: { 'Authorization': `Bot ${globalThis.DISCORD_BOT_TOKEN}` }
          });
          if (resp.ok) {
            const info = await resp.json();
            const mapType = (t) => {
              switch (t) {
                case 0: return 'text';
                case 2: return 'voice';
                case 4: return 'category';
                case 5: return 'announcement';
                case 13: return 'stage';
                case 15: return 'forum';
                default: return 'text';
              }
            };
            name = name || info.name || '';
            type = type || mapType(info.type);
          }
        } catch (_) {}
      }
      const ch = await getJson(key) || [];
      const arr = Array.isArray(ch) ? ch : (Array.isArray(ch.channels) ? ch.channels : []);
      const idx = arr.findIndex(x => String(x.id) === id);
      const next = { id, ...(name && { name }), ...(type && { type: type || 'text' }) };
      if (idx >= 0) arr[idx] = { ...arr[idx], ...next }; else arr.push(next);
      await globalThis.FEEDS_BUCKET.put(key, JSON.stringify(arr, null, 2), { httpMetadata: { contentType: 'application/json' } });
      return jsonResponse({ success: true, channel: next }, 200);
    }
    if (request.method === 'DELETE') {
      const body = await request.json().catch(() => ({}));
      const id = (body.channelId || body.id || '').toString().trim();
      if (!id) return jsonResponse({ error: 'channelId required' }, 400);
      const arr = (await getJson(key)) || [];
      const channels = Array.isArray(arr) ? arr : (Array.isArray(arr.channels) ? arr.channels : []);
      const filtered = channels.filter(ch => String(ch.id) !== id);
      await globalThis.FEEDS_BUCKET.put(key, JSON.stringify(filtered, null, 2), { httpMetadata: { contentType: 'application/json' } });
      return jsonResponse({ success: true }, 200);
    }
  }

  // Admin: fetch single channel info from Discord
  if (request.method === 'POST' && pathname === '/api/channels/fetch-name') {
    if (!isAuthorized()) return jsonResponse({ error: 'Authentication required' }, 401);
    const body = await request.json().catch(() => ({}));
    const id = (body.channelId || body.id || '').toString().trim();
    if (!id) return jsonResponse({ success: false, error: 'channelId required' }, 400);
    if (!globalThis.DISCORD_BOT_TOKEN) return jsonResponse({ success: false, error: 'DISCORD_BOT_TOKEN not configured' }, 400);
    try {
      const resp = await fetch(`https://discord.com/api/v10/channels/${id}`, {
        headers: { 'Authorization': `Bot ${globalThis.DISCORD_BOT_TOKEN}` }
      });
      if (!resp.ok) return jsonResponse({ success: false, error: `discord_http_${resp.status}` }, resp.status);
      const info = await resp.json();
      const mapType = (t) => {
        switch (t) {
          case 0: return 'text';
          case 2: return 'voice';
          case 4: return 'category';
          case 5: return 'announcement';
          case 13: return 'stage';
          case 15: return 'forum';
          default: return 'text';
        }
      };
      return jsonResponse({ success: true, channel: { id, name: info.name || `channel-${id.slice(-4)}`, type: mapType(info.type) } }, 200);
    } catch (e) {
      return jsonResponse({ success: false, error: String(e) }, 500);
    }
  }

  // ---- Admin: feed_map.json (mappings) ----
  if (request.method === 'POST' && pathname === '/api/feed-mappings') {
    if (!isAuthorized()) return jsonResponse({ error: 'Authentication required' }, 401);
    const body = await request.json().catch(() => ({}));
    const feedUrl = (body.feedUrl || body.url || '').toString();
    const channelId = (body.channelId == null ? null : String(body.channelId));
    if (!feedUrl) return jsonResponse({ error: 'feedUrl required' }, 400);
    const key = `${sourcePrefix()}/feed_map.json`;
    const m = await getJson(key) || {};
    if (channelId) m[feedUrl] = channelId; else delete m[feedUrl];
    await globalThis.FEEDS_BUCKET.put(key, JSON.stringify(m, null, 2), { httpMetadata: { contentType: 'application/json' } });
    return jsonResponse({ success: true, mappings: m }, 200);
  }

  // ---- Admin: update feed->group assignment (persisted as group->list) ----
  if (request.method === 'POST' && pathname === '/api/feed-groups') {
    if (!isAuthorized()) return jsonResponse({ error: 'Authentication required' }, 401);
    const body = await request.json().catch(() => ({}));
    const feedUrl = (body.feedUrl || body.url || '').toString().trim();
    const groupName = (body.groupName || body.group || '').toString().trim();
    if (!feedUrl) return jsonResponse({ error: 'feedUrl required' }, 400);
    const key = `${sourcePrefix()}/groups.json`;
    const stored = await getJson(key) || {};
    const groups = toCanonicalGroupMap(stored);
    // Remove feed from all groups
    for (const [g, arr] of Object.entries(groups)) {
      if (!Array.isArray(arr)) continue;
      const idx = arr.indexOf(feedUrl);
      if (idx >= 0) arr.splice(idx, 1);
      if (arr.length === 0) delete groups[g];
    }
    // Add to new group if provided
    if (groupName) {
      if (!groups[groupName]) groups[groupName] = [];
      if (!groups[groupName].includes(feedUrl)) groups[groupName].push(feedUrl);
    }
    await globalThis.FEEDS_BUCKET.put(key, JSON.stringify(groups, null, 2), { httpMetadata: { contentType: 'application/json' } });
    return jsonResponse({ success: true, groups }, 200);
  }

  // ---- Admin: group list management (create/rename/delete) ----
  if (pathname === '/api/groups') {
    if (!isAuthorized()) return jsonResponse({ error: 'Authentication required' }, 401);
    const key = `${sourcePrefix()}/groups.json`;
    if (request.method === 'GET') {
      const stored = await getJson(key) || {};
      const groups = toCanonicalGroupMap(stored);
      return jsonResponse({ groups }, 200);
    }
    if (request.method === 'POST') {
      const body = await request.json().catch(() => ({}));
      const name = (body.groupName || body.name || '').toString().trim();
      if (!name) return jsonResponse({ error: 'groupName required' }, 400);
      const stored = await getJson(key) || {};
      const groups = toCanonicalGroupMap(stored);
      if (!groups[name]) groups[name] = [];
      await globalThis.FEEDS_BUCKET.put(key, JSON.stringify(groups, null, 2), { httpMetadata: { contentType: 'application/json' } });
      return jsonResponse({ success: true, groups }, 200);
    }
    if (request.method === 'PUT') {
      const body = await request.json().catch(() => ({}));
      const oldName = (body.oldName || body.old || '').toString().trim();
      const newName = (body.newName || body.new || '').toString().trim();
      if (!oldName || !newName) return jsonResponse({ error: 'oldName and newName required' }, 400);
      const stored = await getJson(key) || {};
      const groups = toCanonicalGroupMap(stored);
      if (!groups[oldName]) return jsonResponse({ error: 'old_not_found' }, 404);
      if (groups[newName]) return jsonResponse({ error: 'new_already_exists' }, 400);
      groups[newName] = groups[oldName] || [];
      delete groups[oldName];
      await globalThis.FEEDS_BUCKET.put(key, JSON.stringify(groups, null, 2), { httpMetadata: { contentType: 'application/json' } });
      return jsonResponse({ success: true, groups }, 200);
    }
    if (request.method === 'DELETE') {
      const url2 = new URL(request.url);
      const qn = (url2.searchParams.get('name') || '').toString().trim();
      const body = await request.json().catch(() => ({}));
      const bn = (body && (body.groupName || body.name)) ? String(body.groupName || body.name).trim() : '';
      const name = qn || bn;
      if (!name) return jsonResponse({ error: 'groupName required' }, 400);
      const stored = await getJson(key) || {};
      const groups = toCanonicalGroupMap(stored);
      if (!groups[name]) return jsonResponse({ error: 'not_found' }, 404);
      delete groups[name];
      await globalThis.FEEDS_BUCKET.put(key, JSON.stringify(groups, null, 2), { httpMetadata: { contentType: 'application/json' } });
      return jsonResponse({ success: true, groups }, 200);
    }
  }

  return jsonResponse({ error: 'not_found' }, 404);
}

// Module-worker compatibility: export a fetch handler for Wrangler v4
export default {
  async fetch(request, env, ctx) {
    try {
      // Bridge module bindings to globals so existing code paths work
      try {
        if (env) {
          if (env.FEEDS_BUCKET) globalThis.FEEDS_BUCKET = env.FEEDS_BUCKET;
          if (typeof env.DASHBOARD_PREFIX !== 'undefined') globalThis.DASHBOARD_PREFIX = env.DASHBOARD_PREFIX;
          if (typeof env.SOURCE_PREFIX !== 'undefined') globalThis.SOURCE_PREFIX = env.SOURCE_PREFIX;
          if (typeof env.ADMIN_TOKEN !== 'undefined') globalThis.ADMIN_TOKEN = env.ADMIN_TOKEN;
          if (typeof env.DISCORD_BOT_TOKEN !== 'undefined') globalThis.DISCORD_BOT_TOKEN = env.DISCORD_BOT_TOKEN;
          if (typeof env.ADMIN_USER_BINDING !== 'undefined') globalThis.ADMIN_USER_BINDING = env.ADMIN_USER_BINDING;
          if (typeof env.ADMIN_PASS_BINDING !== 'undefined') globalThis.ADMIN_PASS_BINDING = env.ADMIN_PASS_BINDING;
          if (typeof env.RAILWAY_BASE !== 'undefined') globalThis.RAILWAY_BASE = env.RAILWAY_BASE;
          if (typeof env.GITHUB_REPO !== 'undefined') globalThis.GITHUB_REPO = env.GITHUB_REPO;
          if (typeof env.GITHUB_PAT !== 'undefined') globalThis.GITHUB_PAT = env.GITHUB_PAT;
          if (typeof env.GH_BOT_PAT !== 'undefined') globalThis.GH_BOT_PAT = env.GH_BOT_PAT;
          if (typeof env.GH_BOT_TOKEN !== 'undefined') globalThis.GH_BOT_TOKEN = env.GH_BOT_TOKEN;
          if (typeof env.GITHUB_TOKEN !== 'undefined') globalThis.GITHUB_TOKEN = env.GITHUB_TOKEN;
        }
      } catch (_) {}
      return await handleRequest({ request, env, ctx });
    } catch (err) {
      try {
        return new Response(JSON.stringify({ error: 'internal_error', message: String(err) }), { status: 500, headers: jsonCorsHeaders() });
      } catch (_) {
        return new Response('internal_error', { status: 500 });
      }
    }
  }
}
