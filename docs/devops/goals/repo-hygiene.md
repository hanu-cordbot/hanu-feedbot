# Goal: Repo hygiene
Status: todo

Purpose: Prevent accidental exposure of feed URLs, credentials, and other sensitive data. Make repo safe to automate from.

# Checklist:
- [ ] 1.1 Create `ci/hide-feeds` branch with plan and tests
- [ ] 1.2 Add `feeds.example`
- [ ] 1.3 Remove `feeds.txt` from tracking and add to `.gitignore`
- [ ] 1.4 Document recovery plan and backup tags

Human interventions:
- [HUMAN_REQUIRED] History rewrite (BFG/git-filter-repo)

Notes:
- Implementation must be reversible and non-destructive by default.
