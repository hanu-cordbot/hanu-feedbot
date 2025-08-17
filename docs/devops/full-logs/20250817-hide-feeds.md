# 2025-08-17 Hide feeds task full log

Branch: ci/hide-feeds
Actions:
- Created branch `ci/hide-feeds` from main
- Moved `feeds.txt` -> `feeds.example` and added `feeds.txt` to `.gitignore`
- Updated `bot/config.py` to optionally fetch feeds.txt from R2 via `FEEDS_R2_BUCKET`
- Pushed changes and opened PR (branch pushed)

Verification:
- Local tests: pytest quick suite for r2 passed after adding shim
- Manual inspection of diffs shows `feeds.txt` removed from working tree and `feeds.example` added

Artifacts:
- Branch: ci/hide-feeds
- Commits: cce6c79, 0627faa

Notes:
- Next concrete action: upload `feeds.txt` to R2 and set secrets, or keep feeds on host machine and configure runtime pull.
