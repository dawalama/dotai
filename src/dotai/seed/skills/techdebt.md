---
name: Find Tech Debt
trigger: /run_techdebt
category: maintenance
allowed-tools: Read, Grep, Glob, Bash
tags: refactoring, cleanup, code-quality
---

Analyze the codebase to identify technical debt, code duplication, and areas needing refactoring.

## Gotchas

- Not all TODOs are debt — some are legitimate future work. Focus on ones that block or degrade.
- Large files aren't automatically bad — a 500-line file with clear structure beats 10 tiny files with unclear boundaries
- Don't count test code as duplication — test cases should be explicit and self-contained, not DRY
- Dead code detection has false positives — check for dynamic imports, reflection, and plugin systems before flagging

## Inputs

- `scope` (optional): Directory or file pattern to analyze (defaults to entire project)
- `focus` (optional): Specific concern (duplication, complexity, outdated-patterns, dead-code, todos)

## Steps

1. **Find markers**: Search for TODO/FIXME/HACK/XXX comments: `grep -rn 'TODO\|FIXME\|HACK\|XXX' <scope>` — note the age via `git blame`
2. **Check complexity**: Look for functions longer than 50 lines, deep nesting (> 4 levels), and functions with more than 5 parameters
3. **Find duplication**: Scan for repeated function signatures, similar logic blocks, and copy-pasted code with minor variations
4. **Detect dead code**: Look for unused imports, unexported functions with no internal callers, and commented-out code blocks
5. **Check dependencies**: Look for outdated or deprecated dependencies, pinned versions with known vulnerabilities
6. **Review recent churn**: Run `git log --oneline --since="30 days ago" --name-only` to find files changed frequently — high churn often signals unclear abstractions
7. **Cross-reference rules**: Check for patterns that violate project conventions in `.ai/rules.md`
8. **Generate report** organized by severity:
   - **CRITICAL**: Security issues, data loss risks, broken error handling
   - **HIGH**: Duplicated business logic, missing abstractions causing churn
   - **MEDIUM**: Long functions, outdated patterns, stale TODOs
   - **LOW**: Style inconsistencies, minor cleanup opportunities
9. For each finding, include: file:line, description, suggested fix, and estimated effort (trivial/small/medium/large)
10. Offer to fix the highest-priority items that are safe to change

## Examples

- Full scan: "/run_techdebt"
- Focus area: "/run_techdebt scope=src/api/ focus=complexity"
- Pre-PR check: "/run_techdebt scope=$(git diff --name-only origin/main)"
