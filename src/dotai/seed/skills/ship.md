---
name: Ship
trigger: /run_ship
role: ship
category: deployment
allowed-tools: Read, Bash, Write
tags: release, deploy, pr
---

Non-interactive ship workflow: sync, test, push, create PR.

## Gotchas

- Rebase can silently succeed but leave conflicts in files — always run tests AFTER rebase, not before
- Force-pushing to shared branches destroys teammates' work — check if branch has other contributors first
- PR auto-title from commit messages can be misleading if commits were WIP — review before submitting

## Steps

1. Detect base branch (same as /run_review)
2. Run `git fetch origin <base> && git rebase origin/<base>` to sync
3. Run the project's test command (from `.ai/rules.md` or `package.json` test script)
4. If tests pass, push the branch: `git push -u origin HEAD`
5. Create a PR with `gh pr create` — auto-generate title from commits, body from diff summary
6. Output the PR URL

## Examples

- Ship current branch: "/run_ship"
