# Agent activity log

Format (one line per action):

[YYYY-MM-DD HH:MM:SS UTC] [agent/branch] TASK: <module:path> — ACTION: <short> — RESULT: <PASS/FAIL> — ARTIFACTS: <PR/commit/links>

Examples:

[2025-08-17 10:15:00 UTC] [work/20250817-hide-feeds] TASK: goals/repo-hygiene.md#1.3 — ACTION: moved feeds.txt to feeds.example — RESULT: PASS — ARTIFACTS: PR#12 commit abc123

Notes:
- Agents must append exactly one line per completed task and push that change in the same commit that implements the code change. This ties plan updates to code changes.
