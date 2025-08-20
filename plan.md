# Hanu Feedbot — High-level Plan

This repository now uses a modular DevOps plan. The detailed, editable per-goal content lives under `docs/devops/`.

Read this file first, then open the relevant module (for example `docs/devops/goals/repo-hygiene.md`) to focus on a single goal.

Agent rules
-----------
- Do not write long progress entries into `plan.md`. Instead, update the per-goal module and the `docs/devops/Agent-log.md`.
- For each completed task move the module's completed notes into `docs/devops/done/` as a single file named `<YYYYMMDD>-<task-slug>.md`.

Where to find modules
---------------------
- Overview & entry: `docs/devops/00-index.md`
- Per-goal modules: `docs/devops/goals/*.md`
- Templates: `docs/devops/templates/task-template.md`
- Done items: `docs/devops/done/`
- Agent activity log: `docs/devops/Agent-log.md`

Next action (agent)
-------------------
1. If you are an agent, open `docs/devops/00-index.md` and pick the top-priority goal.
2. Work only inside that module. When done, move the completed artifacts to `docs/devops/done/` and add a single log line in `docs/devops/Agent-log.md`.

Generated: 2025-08-17

Top-level checklist
-------------------
- [ ] 0. Safety: create backups and a dev branch
   - [ ] 0.1 git tag backup-before-major && git push origin backup-before-major
   - [ ] 0.2 git checkout -b dev && git push -u origin dev
   - [ ] 0.3 Run unit tests on `dev` (pytest) and fix blocking failures

- [ ] 1. Repo hygiene: hide sensitive files and feeds
   - [ ] 1.1 Create `ci/hide-feeds` branch
   - [ ] 1.2 Add `feeds.example` containing a sanitized list (committed)
   - [ ] 1.3 Remove `feeds.txt` from tracking and add to `.gitignore`
   - [ ] 1.4 Do not rewrite history yet; keep backup tags/branches for recovery
- [x] 1. Repo hygiene: hide sensitive files and feeds
   - [x] 1.1 Create `ci/hide-feeds` branch
   - [x] 1.2 Add `feeds.example` containing a sanitized list (committed)
   - [x] 1.3 Remove `feeds.txt` from tracking and add to `.gitignore`
   - [ ] 1.4 Do not rewrite history yet; keep backup tags/branches for recovery

- [ ] 2. CI & workflows: clean and consolidate workflows
   - [ ] 2.1 Create `ci/clean-workflows` branch
   - [ ] 2.2 Remove hard-coded secrets; use GitHub Actions secrets only
      - [x] 2.3 Validate environment variables early and fail fast (basic validation added)
   - [ ] 2.4 Use a scoped `GH_BOT_PAT` secret for commits from CI (if needed)
   - [ ] 2.5 Add a manual dispatch workflow for testing before scheduling hourly runs
- [x] 2. CI & workflows: clean and consolidate workflows
   - [x] 2.1 Create `ci/clean-workflows` branch (work performed on `ci/hide-feeds`)
   - [x] 2.2 Remove hard-coded secrets; use GitHub Actions secrets only (no secret values printed)
   - [x] 2.3 Validate environment variables early and fail fast (basic validation added; add PR-level YAML validation suggested)
   - [x] 2.4 Use a scoped `GH_BOT_PAT` secret for commits from CI (if needed)
   - [x] 2.5 Add a manual dispatch workflow for testing before scheduling hourly runs (added `test-seen-r2.yml`)

- [ ] 3. Private storage for feeds & secrets
   - [ ] 3.1 Choose storage option (R2 recommended) and add secrets: `FEEDS_R2_BUCKET`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_ENDPOINT`
   - [ ] 3.2 Upload `feeds.txt` to R2 (or SOPS/git-crypt) and verify access
   - [ ] 3.3 Ensure `bot/config.py` fetches `feeds.txt` from R2 when configured
- [x] 3. Private storage for feeds & secrets
   - [x] 3.1 Choose storage option (R2 recommended) and add secrets: `FEEDS_R2_BUCKET` / `SEEN_R2_BUCKET` support added
   - [ ] 3.2 Upload `feeds.txt` to R2 (or SOPS/git-crypt) and verify access
   - [x] 3.3 Ensure `bot/config.py` fetches `feeds.txt` from R2 when configured

- [ ] 4. R2 uploader & video pipeline
   - [ ] 4.1 Verify `r2/uploader.py` supports multi-part and metadata
   - [ ] 4.2 Add CI integration tests (moto or mock) for R2 uploads
   - [ ] 4.3 Create workflow step to upload videos and return public URLs
   - [ ] 4.4 Ensure posts embed R2 URLs and dashboard updates reflect uploads

- [ ] 5. Pages & Admin protection
   - [ ] 5.1 Confirm `update_feed_meta.yml` deploys dashboard to GitHub Pages
   - [ ] 5.2 Implement Cloudflare Worker auth for admin pages using `ADMIN_PASS`
   - [ ] 5.3 Test admin access flow end-to-end (staging first)

- [ ] 6. Monitoring, logging & recovery
   - [ ] 6.1 Keep `backup-before-prune` and restore branches/tags
   - [ ] 6.2 Add CI artifacts and log upload for each run
   - [ ] 6.3 Add a small status page showing last run/time and success
- [ ] 6. Monitoring, logging & recovery
   - [ ] 6.1 Keep `backup-before-prune` and restore branches/tags
   - [x] 6.2 Add CI artifacts and log upload for each run (artifacts and uploads added)
   - [x] 6.3 Add a small status page showing last run/time and success (`docs/devops/last-ci-status.md` created by workflow)

- [ ] 7. (Optional) History sanitization (destructive)
   - [ ] 7.1 Prepare BFG/git-filter-repo plan (backup, timeline, notify collaborators)
   - [ ] 7.2 Run history purge and force-push only after approvals

Per-task minimal contract (what an agent must do for each checklist item)
--------------------------------------------------------------------
For every checkbox the agent ticks, it must produce:

- Preconditions: branch name, secrets required, and expected test environment
- Steps: the exact shell/git commands and the files to change
- Verification: tests to run and expected outputs (PASS/FAIL)
- Postconditions: artifacts or branch created and pointers (PR link, tag name)
- Rollback: exact commands to revert the change (git reset/branch delete/tag restore)

Example: 1.3 Remove `feeds.txt` from tracking
- Preconditions: `ci/hide-feeds` branch, backup tag exists
- Steps:
   - git checkout -b ci/hide-feeds
   - git mv feeds.txt feeds.example
   - echo "feeds.txt" >> .gitignore
   - git add feeds.example .gitignore && git commit -m "ci: move feeds to example and ignore feeds.txt"
   - git push -u origin ci/hide-feeds
- Verification: PR shows removed `feeds.txt` and new `feeds.example`; unit tests unaffected
- Postcondition: feeds are no longer tracked on branch `ci/hide-feeds`
- Rollback: git checkout main; git checkout -b rollback-feeds; git revert <commit> or restore files from backup tag

Secrets & minimal required secrets (store in GitHub Actions):
- DISCORD_BOT_TOKEN
- DISCORD_WEBHOOK_URL (optional)
- CHANNEL_ID, GLOBAL_FALLBACK_CHANNEL_ID
- GEMINI_API_KEY
- R2_* (R2_BUCKET, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_ENDPOINT)
- ADMIN_PASS
- GH_BOT_PAT (scoped for CI commits)
- RAILWAY_JOB_ENDPOINT (optional)

Quality gates
-------------
- Local: run `pytest -q` (quick), fix blocking failures before PR
- CI: run tests + lint and a smoke run on `dev` before merging to `main`
- Post-merge smoke: after merging to `main`, schedule a single manual run and verify Discord posting to a test channel

Short-term next actions (what the agent should do now)
--------------------------------------------------
- [ ] Open PR for `ci/hide-feeds` (branch already pushed)
- [ ] Add R2 secrets and upload `feeds.txt` to R2, or keep `feeds.txt` local to the deployment server
- [ ] Manually dispatch `ci/clean-workflows` on `dev` to verify workflow changes
 - [ ] Add a PR-level YAML validation job to catch invalid expressions (for example, referencing `secrets.*` inside `if:`) before merging workflows

Agent activity log (recent):

- [2025-08-18 10:25:00 UTC] [work/add-dispatch] TASK: add manual-run workflow — RESULT: PR opened (#7) — ARTIFACTS: .github/workflows/run-bot-now.yml

Appendix: commands (PowerShell)
------------------------------
Create dev branch and push:
```powershell
git checkout -b dev
git push -u origin dev
```

Upload feeds.txt to R2 (aws-cli compatible):
```powershell
# on your machine with R2 credentials configured
aws --endpoint-url https://<account>.r2.cloudflarestorage.com s3 cp feeds.txt s3://<bucket>/feeds.txt
```

Run bot locally (after populating `.env`):
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python cron_worker.py
```

Generated: 2025-08-17 — this `plan.md` is intended to be small, machine-friendly, and updated after every milestone.

Agent autopilot prompt & update rules
------------------------------------
Use this template when instructing an agent to act autonomously. The agent MUST follow these rules exactly.

Agent prompt template (copy/paste):
"""
You are an autonomous engineering agent working on the `hanu-feedbot` repo. Your mission: make safe, incremental progress on the checklist in `plan.md`.

Before any change
- Pull latest `main` and `dev`.
- Create a short-lived branch: `work/<ticket>-<short-desc>`.
- Update the `plan.md` section `Agent activity log` with: timestamp, branch, planned checklist item.

Change & commit rules
- Make only the minimal change required to finish the checklist item.
- Run local tests (pytest) that are relevant to the changed area.
- Commit using the format: `task(<area>): <short description> — plan: <plan.md item path>`
- Push the branch and open a PR to `dev` with a short testing checklist and link to this PR in `plan.md`.

Post-merge & update
- After the PR merges to `dev`, run CI smoke tests. If successful, merge `dev` to `main` via PR.
- Immediately update `plan.md`:
   - Mark the checklist item as complete with timestamp and list artifacts (PR URL, commit SHA).
   - Add a one-line summary of verification results.
   - If the change introduced a new subtask, create it under the appropriate tree node.

Human intervention required (stop and wait for human):
- Any destructive history rewrite or force-push (BFG/git-filter-repo).
- Adding or rotating production secrets (must be set in GitHub Secrets or secure vault by a human).
- Creating or revoking credentials with third-party services (Cloudflare, GitHub Apps, R2 accounts).

If you encounter any of the above, stop and update `plan.md` with the issue, proposed options, and a clear, one-line request for human approval.
"""

Agent activity log (automation entries)
--------------------------------------
- This section is for automated updates. Each entry must use this exact format:
   - [YYYY-MM-DD HH:MM:SS UTC] [branch] [PR=# if any] TASK: <plan item path> — RESULT: <pass/fail> — ARTIFACTS: <links>

Per-goal purpose statements (why each goal exists)
-------------------------------------------------
- 0. Safety: create backups and a dev branch
   - Purpose: Ensure we can always recover the repository to a known good state before making changes.
   - Contributes to final goal by enabling reversibility and minimizing risk of lost work.

- 1. Repo hygiene: hide sensitive files and feeds
   - Purpose: Prevent accidental exposure of third-party feed URLs and credentials.
   - Contributes to final goal by securing the data source and making the public repo safe to share and automate from.

- 2. CI & workflows: clean and consolidate workflows
   - Purpose: Provide a single, auditable, and secure automation pipeline that runs the bot hourly and commits safe state changes.
   - Contributes to final goal by ensuring automation runs reliably and only with explicit secrets.

- 3. Private storage for feeds & secrets
   - Purpose: Store sensitive lists and configuration in a private store (R2 or vault) where only CI/runtime can access.
   - Contributes to final goal by removing sensitive data from VCS and enabling secure, automated retrieval during runtime.

- 4. R2 uploader & video pipeline
   - Purpose: Enable reliable upload and serving of large media files while keeping storage cost-effective and under our control.
   - Contributes to final goal by allowing the bot to publish large video content and keeping CDN/streaming stable.

- 5. Pages & Admin protection
   - Purpose: Serve a public dashboard while protecting admin controls behind authenticated Cloudflare Workers.
   - Contributes to final goal by providing observability and a protected control plane for humans to manage the bot.

- 6. Monitoring, logging & recovery
   - Purpose: Detect failures early, retain artifacts for debugging, and provide a playbook to recover from incidents.
   - Contributes to final goal by making the system maintainable and operable long-term.

- 7. History sanitization (destructive)
   - Purpose: Remove past exposures from VCS history when necessary and acceptable.
   - Contributes to final goal by permanently eliminating sensitive data from repo history when required.

Human intervention markers (place these next to checklist entries that require a human)
--------------------------------------------------------------------------------
- [HUMAN_REQUIRED] -> must not be auto-approved
- [HUMAN_REVIEW] -> auto-change allowed but must be reviewed and manually merged by a human

Where to write updates
----------------------
- Always edit `plan.md` in a branch and include the `Agent activity log` entry in the same commit that implements the change. This keeps plan state and code changes tied together for auditability.

Branching & commit conventions for the agent
-------------------------------------------
- Branch name: `work/<YYYYMMDD>-<short-task-slug>` or `work/<ticket>-<short-desc>`
- Commit message: `task(<area>): <short description> — plan: <path>`
- PR title: `work: <short description> — relates to plan.md <path>`

Example update flow (agent)
--------------------------
1. Pick item `1.3` (Remove `feeds.txt` from tracking).
2. Create branch `work/20250817-hide-feeds`.
3. Implement change, run tests locally.
4. Commit with message `task(config): move feeds to feeds.example — plan: 1.3`.
5. Push branch, open PR to `dev` with checklist and tests run log.
6. After merge, update `plan.md` `Agent activity log` with: `[2025-08-17 12:00:00 UTC] [work/20250817-hide-feeds] TASK: 1.3 — RESULT: PASS — ARTIFACTS: PR#123, commit abcdef`.


