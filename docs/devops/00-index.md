# DevOps Modules index

This folder contains modular plans for each high-level goal. Agents should pick one goal at a time and operate only in that module.

Modules:
- goals/repo-hygiene.md
- goals/ci-workflows.md
- goals/feeds-storage.md
- goals/r2-pipeline.md
- goals/admin-auth.md
- goals/monitoring.md

Templates:
- templates/task-template.md

Agent log:
- Agent-log.md

Done:
- done/

Runtime behavior requirement (strict)
-----------------------------------
- Agents MUST follow the exact order in `plan.md` unless a human explicitly reprioritizes.
- For each selected module the agent must:
	1. Open the module file under `docs/devops/goals/` and mark the `Checklist` item as `in-progress` with timestamp.
	2. Perform the minimal edit/work required for that checklist item.
	3. After a successful verification (tests/CI), update the module file to mark the item `done`, move any long notes into `docs/devops/done/<YYYYMMDD>-<slug>.md`, and append a one-line entry in `docs/devops/Agent-log.md`.
	4. Only then pick the next checklist item from the same module or the next module in plan order.

This enforces a strict loop: pick -> mark in-progress -> act -> verify -> mark done -> log -> next.
