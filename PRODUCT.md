# Product direction

## Purpose

dotai is a small, local tool for maintaining and carrying a developer's explicit
engineering judgment across repositories and coding agents.

Engineering judgment includes private standards, architectural decisions, personal
taste, local constraints, exceptions, and lessons deliberately retained from prior work.

> Teach it once. Apply it when relevant. Know what dotai selected and returned, and why.

The durable value is private knowledge that a better model cannot infer. Generic advice
about how to plan, debug, review, or behave like an expert is a shrinking source of value.
Native harness features handle skill discovery, session continuation, execution permissions,
and agent orchestration wherever possible.

## User

The user is an individual developer who uses more than one coding agent, works across
multiple repositories, or cares enough about their development style to make it explicit.
They should not need a platform, team rollout, or hosted memory service to get value.

## Product loop

1. **Capture** a standard, preference, local constraint, or correction.
2. **Approve** what becomes durable developer knowledge.
3. **Resolve** the minimum relevant knowledge for a task and its affected files.
4. **Deliver** it through an adapter or explicit context command.
5. **Explain** what dotai selected and returned, and why.
6. **Audit** knowledge that is stale, conflicting, oversized, or ineffective.
7. **Retire** knowledge without losing control of its source or history.

## Product principles

1. **Developer-approved, never silently learned.** Agents may propose knowledge;
   only the developer promotes it into durable context.
2. **Selective, not exhaustive.** Always-on context is a cost. Load the smallest
   relevant set while keeping mandatory guardrails dependable.
3. **Explicit before inferred.** File scopes, tags, explicit triggers, and precedence
   remain inspectable. Opaque semantic retrieval cannot be the only path for
   security or compliance rules.
4. **Team instructions remain authoritative.** Personal judgment supplements a
   repository; it does not silently take ownership of shared agent files.
5. **Portable, native, and local first.** Knowledge remains readable, versionable files.
   Native `SKILL.md` packages are canonical; no lossy conversion format. Core behavior
   does not require a server, account, or network request.
6. **Observable.** A developer can determine which knowledge dotai selected, why it
   was selected, and whether resolution was provisional. Receipts record selection metadata,
   not claims of agent compliance or causality.
7. **One canonical path.** `context` resolves judgment, adapters deliver it, and
   `sync` prepares a safe local cache. Avoid parallel prompt dumps, watchers,
   and repository-mutation workflows.
8. **Real enforcement over prompt theater.** Prompt instructions do not create a sandbox
   boundary. True enforcement relies on host permissions, tool controls, linters, CI,
   and tests.

## Explicit non-goals

dotai is not:
- A generic workflow library (ordinary engineering instructions like generic planning,
  debugging, code review checklists, or scaffolding).
- A persona catalog or automatic persona injector (roles are retired as a core abstraction;
  perspectives are standard user-authored skills).
- A prompt-based safety sandbox ("careful mode" prompt prefixes or `allowed-tools` prose
  claimed as an enforced boundary).
- A session-bootstrap context dump or handoff orchestrator.
- An implicit keyword-based workflow router (task prose does not trigger random workflows).
- A transcript store, general-purpose agent memory, goal manager, or agent orchestrator.
- A hosted vector database or production observability platform.
- A replacement for repository and organization policy.

## Product focus decision (0.8.0)

As coding models and native agent harnesses improved, generic prompting layers aged rapidly.
In 0.8.0, dotai explicitly narrows its focus to **durable personal developer guidance**—the
private knowledge that even a stronger model cannot infer:

- **Kept and strengthened:** explicit capture and developer approval (`dotai learn`),
  distinct semantics for hard rules versus soft preference packs, deterministic scope and
  precedence across global and project `.ai/` directories, explainable selection receipts,
  safe maintenance (`dotai audit`, `dotai compress`), and lossless native `SKILL.md`
  package storage.
- **Retired from the core product:**
  - *Generic workflow seeds:* fresh `dotai init` no longer installs bundled planning,
    debugging, review, verification, scaffolding, or shipping prompts that merely describe
    ordinary engineering competence.
  - *Roles as a first-class abstraction:* persona catalogs and automatic persona injection
    are retired; concrete constraints and perspectives live in scoped rules or user-authored
    skills, with `dotai migrate` preserving legacy roles losslessly.
  - *Prompt-based careful mode:* removed bundled careful-mode prompts and any claim that
    prompt text or `allowed-tools` metadata creates an enforced safety boundary.
  - *General session-bootstrap dumps:* retired broad handoff/context dumps in favor of
    compact primers, targeted on-demand resolution, and native harness continuation.
  - *Implicit keyword workflow routing:* task prose no longer auto-triggers workflows via
    incidental keyword matching; skills load only when explicitly requested (`--skill`) or
    discovered natively by the harness.
  - *Lossy skill conversion:* native `SKILL.md` packages are stored and loaded with bodies,
    metadata, scripts, references, and assets intact instead of slicing sections into a
    custom intermediate format.

## Decision test

A feature belongs in dotai when it makes private developer judgment easier to capture,
selectively apply, verify, maintain, or carry across agents. It must earn its setup and
execution overhead compared with a small native instruction file and native skill packages.
Features that merely accumulate conversation history or duplicate host capabilities are
rejected.

## Success signals

- A developer teaches private guidance once and sees it selected across different agents.
- Relevant context stays small as the knowledge base grows.
- Users can inspect why a rule, preference, or skill was selected.
- Selection receipts clearly report selection and delivery without exaggerating compliance.
- Audit and usage information causes users to refine or retire outdated guidance.
- dotai saves more repeated correction time than it adds in maintenance.
