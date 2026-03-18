---
name: Learn
trigger: /run_learn
category: workflow
allowed-tools: Read, Bash, Write
tags: learning, rules, feedback
---

Capture a lesson from the current session and turn it into a permanent rule so the mistake never repeats.

## Gotchas

- Rules should be specific and actionable — "be careful with auth" is useless, "always validate Bearer token prefix before API calls" is useful
- Don't create duplicate rules — search existing rules first
- Rules should describe the *correction*, not just the *mistake* — the agent needs to know what TO do
- Keep rules scoped — a rule that applies to everything applies to nothing

## Steps

1. **Identify what went wrong**: Ask the user what happened, or review the recent conversation for corrections, reverts, or "no, instead do X" moments
2. **Search existing rules**: Run `dotai rules` and check `~/.ai/rules.md` to avoid duplicates
3. **Draft the rule** with:
   - A short, descriptive title (e.g. "auth-bearer-prefix", "no-inline-styles")
   - What went wrong (the issue)
   - What to do instead (the correction)
   - File patterns it applies to (globs), if relevant
   - Tags for discoverability
4. **Present the draft** to the user for review before saving
5. **Save the rule**: Use `dotai learn "title" --issue "..." --correction "..."` for inline rules, or create a structured rule file in `~/.ai/rules/` for complex rules
6. **Resync**: Run `dotai sync` so the new rule is immediately active in all agent configs
7. **Confirm**: Show the user where the rule was saved and that it will apply on next session

## Examples

- After a mistake: "/run_learn" → agent reviews what went wrong and proposes a rule
- Explicit learning: "/run_learn Always use parameterized queries, never string concatenation for SQL"
- Scoped learning: "/run_learn React components must use named exports --globs *.tsx"
