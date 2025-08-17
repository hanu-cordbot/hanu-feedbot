# Goal: CI & Workflows
Status: todo

Purpose: Provide secure, auditable, and reliable automation pipelines for hourly runs, deployments, and state commits.

# Checklist:
- [ ] 2.1 Create `ci/clean-workflows` branch
- [ ] 2.2 Remove hard-coded secrets from workflows
- [ ] 2.3 Add validation step for required secrets
- [ ] 2.4 Add manual dispatch and staged rollout to hourly schedule
- [ ] 2.5 Use `GH_BOT_PAT` for state commits (scoped)

Human interventions:
- [HUMAN_REVIEW] Approve creation of `GH_BOT_PAT` and its scope
