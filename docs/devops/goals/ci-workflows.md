# Goal: CI & Workflows
Status: in-progress

Purpose: Provide secure, auditable, and reliable automation pipelines for hourly runs, deployments, and state commits.

# Checklist:
- [x] 2.1 Create `ci/clean-workflows` branch
- [x] 2.2 Remove hard-coded secrets from workflows (dev/test workflows removed)
- [x] 2.3 Add validation step for required secrets (partial: basic env validation added; need PR-level YAML validation)
- [ ] 2.4 Add manual dispatch and staged rollout to hourly schedule
- [ ] 2.5 Use `GH_BOT_PAT` for state commits (scoped)

Notes:
- Fixed invalid expression that referenced `secrets` inside an `if:` and replaced it with an always-run step that checks `GH_BOT_PAT` inside the script (avoids workflow rejection).
- Added a recommended next task: create a pre-merge workflow that validates YAML and disallows `secrets` usage in `if:` expressions.

Human interventions:
- [HUMAN_REVIEW] Approve creation of `GH_BOT_PAT` and its scope
