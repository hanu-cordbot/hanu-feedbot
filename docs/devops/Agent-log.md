# Agent current status (single-entry) and options

This file holds exactly one single-line entry describing the agent's current status and the single next action to take. Use `docs/devops/full-logs/` for full, detailed logs per task or phase.

Format (single entry only):

[YYYY-MM-DD HH:MM:SS UTC] [agent/branch] STATUS: <short status sentence>. NEXT: <one-line next action>. OPTIONS: <option1 | option2 | option3>. ARTIFACTS: <links>

Example:

[2025-08-17 12:30:00 UTC] [ci/hide-feeds] STATUS: Completed moving `feeds.txt` to `feeds.example` and updating config to optionally fetch from R2. NEXT: Choose feed storage approach and upload `feeds.txt`. OPTIONS: (1) Upload to R2 now (recommended) | (2) Keep local and configure server pull | (3) Encrypt with sops/git-crypt and commit. ARTIFACTS: docs/devops/full-logs/20250817-hide-feeds.md

Rules:
- The agent MUST update this file at the start and end of each task iteration.
- Full logs must be written to `docs/devops/full-logs/<YYYYMMDD>-<slug>.md` and referenced in `ARTIFACTS`.
- When marking NEXT, the agent must provide at least two viable OPTIONS and a recommended choice.
- The agent must keep the same final goal in mind; OPTIONS are just alternative paths to reach it.

