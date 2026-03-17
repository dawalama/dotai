---
name: Find Tech Debt
trigger: /run_techdebt
role: reviewer
category: code-quality
allowed-tools: Read, Grep, Glob, Bash
tags: refactoring, cleanup, code-quality
---

Analyze the codebase to identify technical debt, code duplication, and areas needing refactoring.

## Inputs

- `scope` (optional): Directory or file pattern to analyze (defaults to entire project)
- `focus` (optional): Specific concern (duplication, complexity, outdated-patterns, dead-code, todos)

## Steps

1. Search for TODO/FIXME/HACK comments across the codebase
2. Look for functions longer than 50 lines and deep nesting (> 4 levels)
3. Check for unused imports and dead code
4. Look for duplicated code patterns
5. Check for outdated patterns that don't match project conventions (from .ai/rules.md)
6. Generate a prioritized report: location, type, severity, suggested fix

## Examples

- Full scan: "/run_techdebt"
- Focus area: "/run_techdebt scope=src/api/ focus=complexity"
