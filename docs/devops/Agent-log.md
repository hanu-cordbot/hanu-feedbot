
# Agent current status (single-entry) and per-phase turn logs

This file contains exactly one current-status line for the agent's entire run. Detailed, turn-based logs belong in a single per-phase file under `docs/devops/full-logs/`.

Single-entry format (current status):

[YYYY-MM-DD HH:MM:SS UTC] [agent/branch] STATUS: <short status sentence>. NEXT: <one-line next action>. OPTIONS: <opt1 | opt2 | opt3>. ARTIFACTS: <links>

Per-phase log rules (turn-based)
- Each phase (module) must have at most one file in `docs/devops/full-logs/` named `<phase>.md` (for example `hide-feeds.md`).
- If a new independent session starts for the same phase, the agent should create `<phase>-2.md`, `<phase>-3.md`, etc.
- Each per-phase log file is append-only and contains a short, high-level entry per turn in the following format:

	[TURN N] [YYYY-MM-DD HH:MM:SS UTC] ACTION: <one-line description>. RESULT: <PASS/FAIL/IN-PROGRESS>. NOTES: <short notes or link to artifacts>

- The agent must update the single-entry `Agent-log.md` to reflect the current phase status and reference the per-phase log file in `ARTIFACTS`.
- The agent must present multiple OPTIONS in the NEXT field and recommend one; always preserve the final goal.

Example `hide-feeds.md` content (turn-based):

	[TURN 1] [2025-08-17 11:50:00 UTC] ACTION: Move `feeds.txt` to `feeds.example` and ignore `feeds.txt`. RESULT: PASS. NOTES: branch `ci/hide-feeds`, commits cce6c79,0627faa
	[TURN 2] [2025-08-17 12:30:00 UTC] ACTION: Update `bot/config.py` to optionally fetch from R2. RESULT: PASS. NOTES: commit cce6c79

Agent behavior rules summary
- Update `Agent-log.md` single line at start and end of each iteration.
- Append one TURN entry to the relevant per-phase file per action attempt.
- Only create new per-phase files with -2/-3 suffix when a new independent session is started.

