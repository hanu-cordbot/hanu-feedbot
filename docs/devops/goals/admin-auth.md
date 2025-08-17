# Goal: Admin auth (Cloudflare Worker)
Status: todo

Purpose: Protect admin pages with Cloudflare Worker authentication using `ADMIN_PASS` and optional zone-based access.

# Checklist:
- [ ] 5.1 Review `cloudflare/src` worker code
- [ ] 5.2 Implement authentication against `ADMIN_PASS` from secret
- [ ] 5.3 Test worker in staging and integrate with Pages routing
- [ ] 5.4 Document admin access flow and emergency unlock steps

Human interventions:
- [HUMAN_REQUIRED] Rotating `ADMIN_PASS` or changing Worker bindings
