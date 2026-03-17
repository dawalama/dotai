---
name: Careful Mode
trigger: /run_careful
category: workflow
context: production, sensitive
allowed-tools: Read, Grep, Glob
tags: safety, production, cautious
---

Activate production-safety mode. When this skill is active, apply extra caution to all operations — double-check before any mutation, prefer read-only investigation, and flag anything that could affect production systems.

## Gotchas

- This mode should RESTRICT, not expand what the agent does — when in doubt, don't
- Database queries in careful mode should always be SELECT with LIMIT, never UPDATE/DELETE
- File writes should be to new files (not in-place edits) so rollback is trivial
- API calls should be to staging/preview endpoints — never call production APIs directly

## Steps

1. Acknowledge careful mode is active — prefix all responses with ⚠️
2. Before any write/mutation operation, explicitly state what will be changed and ask for confirmation
3. Prefer read-only operations: `git diff` over `git commit`, `SELECT` over `UPDATE`
4. When suggesting changes, always include a rollback plan
5. Flag any operation that touches production data, configs, or infrastructure
6. At the end, summarize all changes made (if any) with rollback instructions

## Examples

- Activate before production work: "/run_careful"
- Investigate prod issue safely: "/run_careful" then "/run_investigate symptom='...' scope=src/api/"
