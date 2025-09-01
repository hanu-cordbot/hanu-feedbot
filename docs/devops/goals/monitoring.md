# Goal: Monitoring & Recovery
Status: in-progress

Purpose: Provide observability, CI artifacts, and a recovery playbook so incidents are easy to diagnose and recover from.

# Checklist:
- [ ] 6.1 Keep backup tags: `backup-before-prune`, `backup-before-major`
- [x] 6.2 Upload logs and artifacts from each workflow run (completed - logs uploaded to artifacts)
- [ ] 6.3 Provide a small status page showing last run and health
- [ ] 6.4 Add simple alerting via Discord webhook for failures

Human interventions:
- [HUMAN_REVIEW] Alerting thresholds and notification channels
