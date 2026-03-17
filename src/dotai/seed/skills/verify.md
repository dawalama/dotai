---
name: Verify
trigger: /run_verify
category: verification
allowed-tools: Read, Grep, Glob, Bash
tags: test, validate, verify
---

Run comprehensive verification on recent changes: tests, types, lint, and build.

## Gotchas

- Don't trust a green test suite alone — check test coverage on changed files specifically
- Type-checking may pass locally but fail in CI due to different tsconfig/mypy settings — use the project's CI command
- Flaky tests that pass on retry mask real issues — note any tests that needed retries
- Build success doesn't mean runtime success — check for runtime-only errors like missing env vars

## Inputs

- `scope` (optional): Limit to specific files or directories
- `quick` (optional): Run only fast checks (lint + types, skip full test suite)

## Steps

1. Detect the project's test/lint/build tooling from config files (package.json, pyproject.toml, Makefile, etc.)
2. Run the linter: `npm run lint`, `ruff check .`, or project equivalent
3. Run type checking: `tsc --noEmit`, `mypy .`, or project equivalent
4. Run tests related to changed files: detect via `git diff --name-only` and run targeted tests
5. Run full build to catch compilation/bundling issues
6. Report results with pass/fail per check, highlighting any warnings or flaky tests

## Examples

- Full verification: "/run_verify"
- Quick lint+types only: "/run_verify quick=true"
