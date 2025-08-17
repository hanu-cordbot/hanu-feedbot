# Goal: Feeds storage

Purpose: Move feeds list into a private store and ensure runtime can securely fetch it.

Checklist:
- [ ] 3.1 Choose storage: R2 (recommended) or encrypted file
- [ ] 3.2 Upload `feeds.txt` to R2 and set secrets
- [ ] 3.3 Verify `bot/config.py` loads feeds from R2 fallback to local
- [ ] 3.4 Add CI test to validate R2 fetch (manual run)

Human interventions:
- [HUMAN_REQUIRED] Creating R2 credentials and uploading feed file
