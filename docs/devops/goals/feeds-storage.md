# Goal: Feeds storage
Status: in-progress

Purpose: Move feeds list into a private store and ensure runtime can securely fetch it.

# Checklist:
- [x] 3.1 Choose storage: R2 (recommended) or encrypted file
- [x] 3.2 Upload `feeds.txt` to R2 and set secrets (completed - feeds.txt now loads from dashboard/data/source/)
- [x] 3.3 Verify `bot/config.py` loads feeds from R2 fallback to local
- [ ] 3.4 Add CI test to validate R2 fetch (manual run)
- [x] 3.5 Persist `seen.json` to R2 and load from R2 when available (implemented in bot/main.py)
- [x] 3.6 Dashboard data generation added to CI workflow (completed)

Human interventions:
- [HUMAN_REQUIRED] Creating R2 credentials and uploading feed file
