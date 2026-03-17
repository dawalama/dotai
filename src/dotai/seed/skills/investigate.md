---
name: Investigate
trigger: /run_investigate
role: debugger
category: debugging
allowed-tools: Read, Grep, Glob, Bash
tags: debug, investigate, root-cause
---

Systematic root-cause investigation for bugs, errors, or unexpected behavior.

## Gotchas

- Don't jump to fixes — the first hypothesis is usually wrong. Gather evidence first
- Stack traces often point to the symptom, not the cause — trace the data flow backward
- Intermittent bugs are often race conditions or state leaks — look for shared mutable state
- Check git blame on suspicious lines — recent changes are more likely to be the cause

## Inputs

- `symptom` (required): What's going wrong (error message, unexpected behavior, reproduction steps)
- `scope` (optional): Where to start looking (file, module, service)

## Steps

1. Reproduce or confirm the symptom — read error logs, stack traces, or user report
2. Form initial hypotheses about the root cause
3. Trace the execution path: find the entry point, follow the data flow through the code
4. Use `git log --oneline -20` and `git blame` on suspicious files to find recent changes
5. Check for common culprits: missing null checks, wrong assumptions about data shape, off-by-one errors, async timing
6. Narrow down to the root cause with evidence (specific line, specific condition)
7. Propose a minimal fix with explanation of why it addresses the root cause
8. Identify whether the same class of bug exists elsewhere using Grep

## Examples

- Debug an error: "/run_investigate symptom='TypeError: Cannot read property of undefined in UserService.getProfile'"
- Investigate behavior: "/run_investigate symptom='payments occasionally fail with timeout' scope=src/payments/"
