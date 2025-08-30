

// Module-worker compatibility: export a fetch handler for Wrangler v4
export default {
  async fetch(request, env, ctx) {
    try {
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