---
name: Plan
trigger: /run_plan
category: workflow
allowed-tools: Read, Grep, Glob, Bash
tags: planning, architecture, design
---

Structured planning workflow: clarify the problem, explore the solution space, produce a concrete plan, then get alignment before writing code.

## Gotchas

- Plans that skip the "why" go stale immediately — always start with the problem, not the solution
- Overly detailed plans break on first contact with the code — keep steps actionable but not prescriptive
- Planning without reading the existing code produces fantasy architectures — always ground in reality first
- A plan nobody reviews is just a TODO list — always end with explicit alignment before execution

## Inputs

- `scope` (optional): What to plan (feature, refactor, migration, bugfix)
- `depth` (optional): quick (5 min outline), standard (full plan), deep (architecture + tradeoffs)

## Steps

1. **Clarify the goal**: State what we're trying to achieve and why. If unclear, ask questions first.
2. **Read the relevant code**: Use Grep and Glob to understand the current state — what exists, what patterns are used, what constraints apply.
3. **Identify the approach**: List 2-3 possible approaches with tradeoffs (complexity, risk, effort, maintainability).
4. **Recommend one approach** with a clear rationale for why it wins.
5. **Break into steps**: Decompose into ordered, independently-verifiable steps. Each step should be small enough to review in isolation.
6. **Identify risks**: What could go wrong? What assumptions are we making? What do we not know yet?
7. **Present the plan** in a structured format and ask for alignment before proceeding.

## Examples

- Plan a feature: "/run_plan scope=feature"
- Quick outline: "/run_plan depth=quick"
- Architecture deep-dive: "/run_plan as systems-architect depth=deep"
- Product-focused plan: "/run_plan as product-manager"
