# Goal: Feeds storage
Status: todo

Purpose: Move feeds list into a private store and ensure runtime can securely fetch it.

# Checklist:
- [x] 3.1 Choose storage: R2 (recommended) or encrypted file
- [ ] 3.2 Upload `feeds.txt` to R2 and set secrets
- [x] 3.3 Verify `bot/config.py` loads feeds from R2 fallback to local
- [ ] 3.4 Add CI test to validate R2 fetch (manual run)
- [x] 3.5 Persist `seen.json` to R2 and load from R2 when available (implemented in bot/main.py)

Human interventions:
- [HUMAN_REQUIRED] Creating R2 credentials and uploading feed file
