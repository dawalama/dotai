# Product direction

## Purpose

dotai carries a developer's engineering judgment across coding agents.

Engineering judgment includes standards, architectural choices, personal taste,
safety and compliance guardrails, repeatable workflows, and lessons deliberately
retained from prior work.

> Teach it once. Apply it when relevant. Know what influenced the agent.

## User

The initial user is an individual developer who uses more than one coding agent,
works across multiple repositories, or cares enough about their development style
to make it explicit. They should not need a platform, team rollout, or hosted
memory service to get value.

## Product loop

1. **Capture** a standard, preference, workflow, or correction.
2. **Approve** what becomes durable developer knowledge.
3. **Resolve** the minimum relevant knowledge for a task and its affected files.
4. **Deliver** it through an adapter or explicit context command.
5. **Explain** what was selected and why.
6. **Audit** knowledge that is stale, conflicting, oversized, or ineffective.
7. **Retire** knowledge without losing control of its source or history.

## Product principles

1. **Developer-approved, never silently learned.** Agents may propose knowledge;
   only the developer promotes it into durable context.
2. **Selective, not exhaustive.** Always-on context is a cost. Load the smallest
   relevant set while keeping mandatory guardrails dependable.
3. **Explicit before inferred.** File scopes, tags, task aliases, and precedence
   remain inspectable. Opaque semantic retrieval cannot be the only path for
   security or compliance rules.
4. **Team instructions remain authoritative.** Personal judgment supplements a
   repository; it does not silently take ownership of shared agent files.
5. **Portable and local first.** Knowledge remains readable, versionable files.
   Core behavior does not require a server, account, or network request.
6. **Observable.** A developer can determine which knowledge was selected, why it
   was selected, and whether resolution was provisional.
7. **One canonical path.** `context` resolves judgment, adapters deliver it, and
   `sync` only prepares a safe local cache. Avoid parallel prompt, index, watcher,
   and repository-mutation workflows.

## Near-term roadmap

### Now: make judgment first-class

- Let developers capture proactive directives as well as corrections.
- Describe rules as codified judgment rather than only mistake prevention.
- Preserve the hard-rule versus soft-preference distinction.
- Keep adapters automatic and resolution explainable.
- Derive local usage counts, last-selected timestamps, and unused knowledge from
  bounded metadata-only receipt history.

### Next: propose improvements

- Let agents draft proposed lessons from explicit developer corrections, with a
  mandatory preview and approval step.
- Add another adapter only where it removes repeated setup for real users.

### Later, only with evidence

- Effectiveness signals beyond selection counts.
- More expressive conflict reporting between personal and team instructions.
- Optional semantic discovery as a convenience layer, never as the sole path for
  mandatory rules.

## Explicit non-goals

dotai is not currently a transcript store, general-purpose agent memory, goal
manager, agent orchestrator, autonomous self-editing instruction system, hosted
vector database, production-agent observability platform, or replacement for
repository and organization policy.

## Decision test

A feature belongs in dotai when it makes developer judgment easier to capture,
selectively apply, verify, maintain, or carry across agents. It should also reduce
repeated correction or setup without making every interaction heavier. Features
that merely accumulate history or orchestrate agents need separate evidence.

## Success signals

- A developer teaches a rule once and sees it applied by another agent.
- Relevant context stays small as the knowledge base grows.
- Users can explain why a rule, preference, role, or skill was selected.
- Audit and usage information causes users to improve or retire knowledge.
- dotai saves more repeated correction time than it adds in maintenance.
