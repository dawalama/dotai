---
name: Learn
trigger: /run_learn
category: workflow
allowed-tools: Read, Bash, Write
tags: learning, rules, feedback
---

Capture engineering judgment from the current session and turn it into a **structured rule** that agents can apply when relevant. This may be a proactive standard or a lesson from a correction.

## Gotchas

- Rules should be specific and actionable — "be careful with auth" is useless, "always validate Bearer token prefix before API calls" is useful
- Don't create duplicate rules — search existing rules first (`dotai rules`, `dotai search`)
- Rules should contain an actionable directive — the agent needs to know what to do
- Keep rules scoped — a rule that applies to everything applies to nothing
- Prefer structured rules in `rules/` over freeform `rules.md` journal entries
- Always dry-run or present the draft before writing when the lesson is ambiguous

## Steps

1. **Identify the judgment**: Capture an explicit standard or review the recent conversation for corrections, reverts, and "instead do X" moments
2. **Search existing rules**: Run `dotai rules` and `dotai search "<keyword>" --type rule`. Also skim `~/.ai/rules.md`. Skip if a good rule already exists
3. **Draft the rule** with:
   - A short, descriptive title (e.g. `auth-bearer-prefix`, `no-inline-styles`)
   - What to do — write this as a direct instruction the agent can follow
   - What went wrong, only when a correction provides useful rationale
   - File patterns (`--globs`) if relevant
   - Tags for discoverability
4. **Preview** with dry-run:
   ```bash
   dotai learn "title" --directive "what to do" -g "*.tsx" -t "react" --dry-run
   ```
5. **Present the draft** to the user for review before saving
6. **Save the structured rule** (default path — creates `~/.ai/rules/<id>.md`):
   ```bash
   dotai learn "title" --directive "..." -g "..." -t "..."
   ```
   Use `--force` only if intentionally replacing a similar rule. Use `-p <project>` for project-scoped rules.
7. **Resync** so agents see the rule:
   ```bash
   dotai learn "title" -i "..." -c "..." --sync
   # or
   dotai sync
   ```
8. **Confirm**: Show the user the rule path and that it will apply on the next session

## Examples

- Proactive taste: `/run_learn` → agent drafts a directive, dry-runs a rule, saves on approval
- After a mistake: `/run_learn` → agent turns the correction into an actionable directive
- Explicit learning: `/run_learn Always use parameterized queries, never string concatenation for SQL`
- Scoped learning: `/run_learn React components must use named exports` with globs `*.tsx`
- Migrate old agent files: `dotai import-agent CLAUDE.md --dry-run` then import (not this skill)
