---
name: Code Review
trigger: /run_review
role: reviewer
category: code-quality
allowed-tools: Read, Grep, Glob, Bash
tags: review, quality, pr
---

Analyze the current branch's diff against the base branch for structural issues that tests don't catch.

## Gotchas

- Large diffs (>500 lines) should be split into per-file reviews — reviewing everything at once causes missed issues
- Always verify the base branch before diffing — stale base branches produce phantom findings
- Renamed/moved files show as delete+add in diffs — don't flag these as "missing" code
- Generated files (lockfiles, compiled output, migrations) should be skimmed, not reviewed line-by-line

## Inputs

- `target` (optional): Specific files, "staged" for staged changes, or omit for branch diff (default: branch diff)
- `depth` (optional): quick, standard, thorough (default: standard)

## Steps

1. Detect the base branch: check `gh pr view --json baseRefName` first, then fall back to `gh repo view --json defaultBranchRef`, then `main`
2. Run `git fetch origin <base> --quiet && git diff origin/<base> --stat` to verify there are changes
3. Read the full diff with `git diff origin/<base>`
4. For each changed file, check for:
   - Correctness: logic errors, off-by-one, null checks, type issues
   - Security: SQL injection, XSS, unvalidated inputs, hardcoded secrets
   - Performance: N+1 queries, unnecessary re-renders, missing indexes
   - Error handling: swallowed exceptions, empty catch blocks
   - Race conditions, auth bypass, trust boundary violations
5. Search changed files for leftover TODOs: `grep -rn 'TODO\|FIXME\|HACK' <files>`
6. Generate a structured report: CRITICAL / HIGH / MEDIUM findings with file:line references and suggested fixes
7. Summarize: approve, request changes, or needs discussion

## Examples

- Review current branch: "/run_review"
- Review specific file: "/run_review target=src/api/auth.py depth=thorough"
- Quick review: "/run_review depth=quick"
