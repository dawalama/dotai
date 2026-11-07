# dotai

**Portable engineering judgment for coding agents.**

dotai carries your private engineering guidance across coding agents. Keep your standards, local constraints, preferences, and custom workflows in `~/.ai/`; dotai selects and returns only the guidance each task needs without taking ownership of team files.

```text
~/.ai/ ── dotai context ── relevant rules + preferences + explicit skill
   │
   └──── dotai sync ────── local context cache (outside Git repositories)
```

Teach it once. Apply it when relevant. Know what dotai selected and returned, and why. No server, account, or proprietary memory layer—just portable Markdown that you own.

## The short version

| You want to… | Use |
|---|---|
| Teach agents a standard, taste, or guardrail | `dotai learn --directive` |
| Use dotai automatically in Claude Code (user-level adapter) | `dotai agent setup claude --apply` |
| See what dotai selected and returned for Claude | `dotai agent last claude` |
| Resolve context portably in any other agent or script | `dotai context` / `dotai primer` |
| Prepare a safe per-repository cache | `dotai sync` |
| Migrate legacy folder skills (`main.md`) or roles to `SKILL.md` | `dotai migrate` |

The default is personal and repository-safe. Team instructions stay authoritative.

## Make every agent work like yours

You prefer derived state over synchronization effects. You reproduce bugs before fixing them. You never allow credentials in logs. These are different kinds of judgment, but they all shape how you build software—and they should not disappear when you change agents.

dotai turns that judgment into durable, reusable instructions:

- **Rules codify decisions.** Capture standards, architectural taste, local constraints, and compliance requirements; scope them by project or file pattern.
- **Skills are native workflow packages.** Maintain repeatable, private, or team procedures using canonical `SKILL.md` packages with scripts, references, and assets intact.
- **Perspectives provide guidance.** Express concrete constraints and review criteria directly in scoped rules or user-authored skills.
- **Preference packs carry your taste.** Share softer choices without weakening hard rules.
- **Adapters fit normal workflows.** Configure a supported agent (such as Claude Code) or use portable CLI resolution (`dotai context`) across any harness.

Rules can be proactive or learned from a correction:

```text
teach a standard ───────────────┐
                               ├─→ approve → resolve when relevant → verify what loaded
correct an agent → keep lesson ┘
```

dotai is deliberately not an autonomous history of every conversation. It is the small, developer-approved part of memory important enough to be explicit, portable, scoped, and auditable.

## See it in action

```bash
# Set up your global knowledge base
dotai init

# Teach every agent a scoped engineering preference admitting justified exceptions
dotai learn "react-hooks-derived-state" \
  --directive "Derive state during render instead of syncing via useEffect; allow useEffect only for external synchronization with cleanup" \
  --globs "*.tsx,*.ts" \
  --tags "react,taste"

# Prepare that knowledge for the current project
cd ~/my-project
dotai sync
```

For automatic delivery in Claude Code, configure the user-level adapter once:

```bash
dotai agent setup claude
dotai agent setup claude --apply
```

Then develop naturally. When starting substantial work, Claude queries dotai for applicable guidance and expands matching file-scoped rules:

```bash
# Or resolve context explicitly on demand:
dotai context --path . --files src/api.ts,src/hooks.ts
```

## Installation

### From PyPI (recommended)

```bash
pip install dotai-cli
```

### With pipx (isolated install)

```bash
pipx install dotai-cli
```

### From source

```bash
git clone https://github.com/dawalama/dotai.git
cd dotai
pip install -e ".[dev]"
```

Requires Python 3.11 or later.

## Quick Start

```bash
dotai init

# See what's available
dotai rules
dotai prefs
dotai skills

# Prepare agent context for a project
cd ~/my-project
dotai sync
```

`dotai sync` always writes personal context under `~/.config/dotai/contexts/` and leaves team-owned files such as `CLAUDE.md`, `AGENTS.md`, and `.claude/skills/` untouched. Existing repository instructions are copied into the local context as the authoritative layer; personal dotai rules and preferences are explicitly supplemental.

Local context storage does not, by itself, make an agent load the context. Until an agent adapter is configured, use `dotai primer --path .` to print a compact bootstrap for pasting or piping into your agent.

dotai uses progressive disclosure to keep prompts small. Compact primers include complete universal directives, a count of file-scoped rules, and active preference/skill catalogs. Unrelated scoped rules are not listed individually. Expand what a task needs:

```bash
# Expand rules matching the affected files
dotai context --path . --files src/api.py,tests/test_api.py

# Expand security-tagged rules and an active CLI preference pack
dotai context --path . --context security --domain cli

# Load one complete skill explicitly
dotai context --path . --skill deploy
```

Selection is deterministic: file globs, explicit context tags, active preference domains, and explicitly requested skills. dotai does not guess from semantic similarity or incidental task keywords. Every expanded item includes the reason it was selected.

`context` and `primer` share the same scoped catalog. Within a Git worktree,
dotai loads global knowledge and applicable ancestor knowledge directories down
to the invocation directory, honoring registered custom `ai_dir` paths. Outside
Git, discovery stops at the nearest registered project, or uses only the supplied
directory when it is unregistered. Unrelated registered projects are not read.
Local definitions override inherited items with the same ID; a disabled local
rule masks the inherited definition. A project's `disabled_rules` list excludes
global definitions while allowing explicit local replacements.

Affected files are relative to `--path` (absolute paths also work). Project rule
globs are relative to the directory owning that project's knowledge; global
globs use the repository or project root. Matching uses logical file paths,
including symlink names. The host remains responsible for filesystem permissions.

The resolver includes complete universal rule bodies and applicable `rules.md`
notes. Active `general` preference packs load by default. Other active domains
are listed without their bodies; select one with `--domain cli`, or load a named
pack directly with `--with-prefs <id>` regardless of its domain. Explicit packs
remain subject to scope and enabled state.

### Automatic delivery (Claude Code) vs. portable CLI resolution

`dotai context` and `dotai primer` provide portable manual resolution for any coding agent or script. For **Claude Code**, dotai also includes a dedicated user-level adapter so you do not have to run `dotai context` manually during normal work. Install it once:

```bash
# Preview the user-memory change
dotai agent setup claude

# Back up existing memory and install it
dotai agent setup claude --apply

# Confirm activation
dotai agent status claude

# See the most recent context dotai selected and returned for Claude
dotai agent last claude
```

The adapter adds a small marker-managed block to `~/.claude/CLAUDE.md`, which
Claude Code loads as user memory across projects. It tells Claude to resolve
dotai context for substantial development work, after affected files are known,
and to avoid repeated calls when no file-scoped rules apply or the task has not
changed. Repository and organization instructions remain authoritative.

When file-scoped rules exist, a resolution without `--files` is explicitly
marked provisional. Claude resolves again after discovering the affected
files. `dotai agent last claude` reports whether the latest resolution is
`provisional` or `resolved`, and whether file scope was provided or remains
unknown. Supplied files do not prove that every affected file was discovered.

The adapter does not modify repositories, install a persistent process, or use
MCP. Existing personal Claude instructions are preserved. To remove only
dotai's block:

```bash
dotai agent remove claude
dotai agent remove claude --apply
```

Setup and removal preview by default. Applied changes back up the prior Claude
memory under `~/.config/dotai/backups/agents/claude/`.

`dotai agent last claude` reads a local receipt written only when the Claude
adapter invokes the resolver. It reports selection metadata and reasons, but
never stores source contents, expanded prompts, credentials, or telemetry.

### Understanding what dotai selected and returned

`dotai insights` aggregates local resolution receipts so you can see what
dotai selected and returned over time:

```bash
dotai insights
dotai insights --agent claude
dotai insights --project my-app
dotai insights --json
```

The report shows complete versus provisional resolutions, selection counts,
last-selected timestamps, universal-rule exposure, and enabled items
that have never been selected in the current window. Receipts record what dotai
selected and returned, and why—they do not prove agent ingestion, compliance,
or causal influence. Likewise, frequent selection does not prove usefulness,
and rare selection does not imply obsolescence: rare safety or migration
constraints may still be critical when their file scopes or tags match.

History contains metadata only and is stored under
`~/.config/dotai/receipts/history/`. It never includes expanded bodies, prompts,
source contents, or credentials. History is bounded to the latest 500 receipts
per agent and never leaves the machine.

If no receipt appears, refresh the adapter and start a new Claude Code session:

```bash
dotai agent setup claude --apply
dotai agent status claude
```

Setup pins the dotai executable used to install the adapter, avoiding an older
`dotai` elsewhere on `PATH`. Receipt persistence is best-effort: if its local
directory is unavailable, Claude still receives resolved context and dotai emits
a warning instead of blocking the task.

## Usage

### Daily workflow

```bash
# Start of day: refresh local context for the project you're working on
cd ~/my-project
dotai sync

# Print the context for an agent that uses portable CLI resolution
dotai primer --path .
```

With the Claude adapter installed, daily use is simpler: open Claude Code and
ask for the work normally. Claude invokes the pinned dotai executable, resolves
applicable guidance, and resolves again with affected files when file-scoped rules
apply. Use `dotai agent last claude` whenever you want to verify what was selected.

### Using skills

dotai adopts native `SKILL.md` packages. Load a skill explicitly by name or trigger:

```bash
# Resolve an explicit skill for a task
dotai context --path . --skill deploy

# List skills filtered by category
dotai skills --category deployment
```

### Teaching your engineering judgment

`dotai learn` creates a **structured rule file** in `~/.ai/rules/` by default. Use a directive for a standard you already hold; use an issue and correction when an agent interaction teaches you something new.

```bash
# Proactively encode a scoped engineering preference admitting justified exceptions
dotai learn "react-hooks-derived-state" \
  --directive "Derive state during render instead of syncing via useEffect; allow useEffect only for external synchronization with cleanup" \
  --globs "*.tsx,*.ts"

# Preview a mandatory local constraint without writing
dotai learn "auth-header" \
  --issue "Forgot Bearer prefix on API token" \
  --correction "Always prepend 'Bearer ' to auth tokens" \
  --dry-run

# Save a structured rule and refresh local context
dotai learn "auth-header" \
  -i "Forgot Bearer prefix on API token" \
  -c "Always prepend 'Bearer ' to auth tokens" \
  --sync

# Import a detailed rule from a file
dotai learn "react-hooks-derived-state" --from-file react-rules.md --globs "*.tsx,*.ts"

# Or ask an adapted agent naturally
> Capture what we learned as a rule.

# Disable a rule for one legacy project
dotai toggle react-hooks-derived-state --off --project legacy-app

# Audit rule quality (duplicates, empty bodies)
dotai rules --check
```

The loop: **teach or correct → review the structured rule → dotai resolves it for the next matching task → inspect what loaded.**

### Keeping rules healthy

Knowledge gets noisy as it grows. `dotai audit` reviews the effective ruleset locally and deterministically—nothing is sent to an external model.

```bash
# Find weak, generic, preference-like, oversized, or overlapping rules
dotai audit
dotai audit --project my-app

# Machine-readable output or a CI quality gate
dotai audit --json
dotai audit --fail-on high
```

The report includes stable finding codes, evidence, suggested actions, an estimated prompt-token cost, and a context-concentration summary showing which rules dominate the budget. Large-rule findings show the rule's share of total context, change risk, reviewable sections, and a conservative manual-savings range. Security and other high-consequence rules receive preservation-first guidance and are deliberately protected from “the model probably knows this” recommendations.

`dotai compress` turns high-confidence findings into a conservative plan. Semantic rewriting is handled by you or your active coding agent, not a hidden provider inside the CLI:

```bash
# Inspect candidates (or emit --json for review)
dotai compress
dotai compress --json

# Validate, back up, and apply an approved versioned proposal
dotai compress apply proposal.json
```

Near-duplicates, generic guidance, and rules that may belong in a preference pack remain suggestions unless you explicitly approve a concrete `proposal.json` and pass it to `dotai compress apply`.

When no exact duplicates exist, compression says there are no **safe automatic** savings while still listing semantic review candidates and their estimated savings. These estimates are directional diagnostics—they help prioritize review rather than proving behavioral improvement. The CLI never invents a semantic rewrite or calls an external provider.

Proposal files are versioned and bound to the original rule with a SHA-256 hash, so stale or renamed rules are rejected. Before applying approved changes, dotai validates every proposed rule and creates a complete timestamped snapshot under the applicable `.ai/backups/<timestamp>-compress/`. After writing, the manifest is finalized with actual before/after hashes, per-rule token savings, total savings, and completion status. Subsequent audits show recently compressed rules and clearly note when a successful reduction remains above the large-rule threshold. Backups are ordinary local files and are never deleted automatically.

### Migrating existing agent files

Already have a `CLAUDE.md`, `.cursorrules`, or `AGENTS.md`? Import user-authored content into `~/.ai/`:

```bash
# Preview
dotai import-agent CLAUDE.md --dry-run

# Append into project .ai/rules.md (default)
dotai import-agent CLAUDE.md

# One structured rule
dotai import-agent .cursorrules --mode rule --name project-conventions

# One rule per ## section
dotai import-agent AGENTS.md --mode sections --dry-run

# Scan a project directory for known agent files
dotai import-agent . --mode rules_md
```

dotai strips its own managed marker sections so you don't re-import generated primers. Directory imports combine all discovered agent files into one update, and structured-rule imports choose a new suffixed filename rather than overwrite an existing rule. Preview unfamiliar files with `--dry-run` before importing.

### Preference packs (taste) — borrowable soft style

Hard rules are law. **Preference packs** are soft taste: CLI stack, design micro-details, export style — things that are too granular or fluid for hard rules. You can author them, pull someone else's, and activate them per project.

**Precedence:** hard rules → freeform `rules.md` → active preference packs → model default.

```bash
# Create a pack
dotai prefs new "CLI Conventions" --domain cli
# Edit ~/.ai/preferences/cli-conventions.md, then activate:
dotai prefs use cli-conventions
dotai sync

# Borrow / pull someone else's taste (local file or git repo)
dotai prefs pull ./design-eng-taste.md --name design-eng --domain design
dotai prefs pull https://github.com/org/taste-packs -n cli
dotai prefs use design-eng

# List / show / deactivate
dotai prefs
dotai prefs show cli-conventions
dotai prefs unuse design-eng

# Project operations stay inside that project; global removal is explicit
dotai prefs use cli-conventions --project my-app
dotai prefs remove cli-conventions --global
```

Preference lookup and removal are scope-safe: a project command cannot mutate a pack owned by another registered project. Removing a pack also removes it from the activation list for the pack's owning scope.

Example pack (`~/.ai/preferences/cli.md`):

```markdown
---
name: CLI Conventions
id: cli
description: How I build CLIs
domain: cli
tags: typescript, commander
---

## Soft preferences

Hard rules always take precedence if they conflict.

### Stack
- TypeScript + tsup
- Commander.js
- Vitest
- pnpm (npm link for local bins)

### Style
- Lowercase `-v` for version
- Start version at `0.0.1`
- Commands live under `commands/`
```

### Searching your knowledge

Search reads the same scoped catalog as `dotai context`. From a project, it
includes global knowledge and applicable ancestor directories, and it skips
unrelated registered projects. Pass `--path` to search another directory.

```bash
# Search by keyword
dotai search "derived state"

# Filter by type
dotai search "deploy" --type skill

# Filter by tag
dotai search --tag security

# Combine filters
dotai search "auth" --type rule --tag react
```

### Multi-project setup

```bash
# Initialize project-local overrides
dotai init ~/my-project
dotai init ~/other-project

# Each project can have its own rules, preferences, and skills in .ai/
# Project-level rules override global ones during sync
```

## Directory Structure

```
~/.ai/                          # Global (cross-project)
├── rules.md                    # Inline rules, conventions, and lessons learned
├── rules/                      # Structured rules (hard constraints)
│   └── auth-bearer-prefix.md   # Example: require Bearer prefix on API tokens
├── preferences/                # Soft taste packs (borrowable style priors)
│   └── cli.md                  # Example: CLI stack / micro-style
├── preferences-active.json     # Which preference packs are active
├── backups/                    # Local snapshots created before migration/compression
├── skills/                     # Native SKILL.md packages and workflows
│   └── deploy/                 # Canonical native package
│       ├── SKILL.md            # Preserved verbatim with scripts/assets intact
│       ├── scripts/
│       ├── assets/
│       └── config.json
├── roles/                      # Transitional (legacy custom roles; migrate via dotai migrate)
└── tools/                      # Python tool implementations
    └── *.py

<project>/.ai/                  # Per-project overrides
├── rules.md                    # Project-specific rules and conventions
├── rules/                      # Project-specific structured rules
├── skills/                     # Project-specific skills
└── tools/                      # Project-specific tools
```

## Skills

dotai adopts native `SKILL.md` packages as the canonical format across coding harnesses.
A fresh installation contains no mandatory library of generic engineering advice; you
maintain private, team, or repository workflows that carry your specific procedures.

Skills can be single Markdown files or native package directories:

```
~/.ai/skills/deploy/
├── SKILL.md         # Canonical skill definition (frontmatter + intact body)
├── scripts/         # Shell/Python scripts the agent can invoke
│   ├── health-check.sh
│   └── rollback.py
├── assets/          # Templates, reference docs, configs
│   └── pr-template.md
└── config.json      # User-specific configuration
```

Native packages preserve package bodies, metadata, companion scripts, references, assets,
and relative file links losslessly without rewriting them into a custom intermediate format.
Folder packages enable progressive disclosure: the agent reads `SKILL.md` for workflow
instructions and accesses helper scripts only when needed.

## Roles & Migration

Roles (cognitive personas) are retired as a first-class product abstraction. Concrete
constraints, review criteria, and architectural guidelines belong in scoped rules or native
skills.

If you have existing role files in `~/.ai/roles/`:
- dotai continues to read them for backward compatibility so your content is never lost.
- Use `dotai migrate` to migrate legacy roles into user-authored perspective skills:

```bash
# Preview migration without modifying disk
dotai migrate --dry-run

# Migrate legacy folder skills (main.md -> SKILL.md) and roles to skills
dotai migrate
```

Migrated skills preserve full personas, principles, and anti-patterns losslessly in
`~/.ai/skills/<role-id>/SKILL.md`.

## Rules

Rules are structured coding standards that agents load deterministically when relevant
files or contexts match. Prompt guidance informs the model; true enforcement belongs
to host permissions, tool sandboxes, linters, tests, and CI.

### Structured Rules

Individual rule files live in `~/.ai/rules/` with frontmatter:

```markdown
---
name: react-hooks-derived-state
description: Compute derived state during render; use useEffect only for external store sync
globs: "*.tsx, *.ts"
tags: react, hooks
enabled: true
---

Compute derived state during render or use event handlers instead of chaining
state updates through useEffect. Allow useEffect only for external synchronization
or subscriptions with cleanup.
```

### Managing Rules

```bash
# List active rules
dotai rules

# Audit duplicates / empty bodies
dotai rules --check

# Import a rule from an external file
dotai learn "react-hooks-derived-state" --from-file react-rule.md --globs "*.tsx,*.ts"

# Record a learning as a structured rule (default)
dotai learn "auth-header" --issue "Forgot Bearer prefix" --correction "Always prepend Bearer to tokens"

# Preview first
dotai learn "auth-header" -i "..." -c "..." --dry-run

# Disable a rule globally
dotai toggle react-hooks-derived-state --off

# Disable a rule for a specific project only
dotai toggle react-hooks-derived-state --off --project my-legacy-app

# Re-enable
dotai toggle react-hooks-derived-state --on
```

Synced local context contains a compact bootstrap: full universal directives, a scoped-rule count, and preference and skill catalogs. Use `dotai context` to expand relevant material on demand.

## Agent Sync

`dotai sync` prepares repository-safe local context with:

- **Complete universal structured directives** (always visible)
- **A count and resolver pointer for file-scoped rules**
- **Pointers to freeform `rules.md` conventions**
- **Skill catalogs** (names, triggers, categories — not full workflows)
Context is always written outside the worktree. Team instructions take precedence over personal dotai rules and preferences. dotai does not attempt unreliable keyword-based conflict resolution; the generated context tells the agent to ignore conflicting personal guidance and ask when a disagreement is ambiguous.

```bash
# Generate outside the repository
dotai sync

# Preview the resolved mode and target without writing
dotai sync --check

# Print primer to stdout (for piping)
dotai primer
dotai primer --path .

# Resolve task-specific context on demand
dotai context --path . --files src/app.tsx --context security
dotai context --path . --skill deploy
```

Use the Claude Code adapter (`dotai agent setup claude --apply`) for automatic delivery in Claude Code. For any other agent, paste or pipe `dotai primer --path .`, then use `dotai context` for task-specific expansion.

## Installing Skills

Install skills from git repos or local directories. Native `SKILL.md` packages are stored losslessly with their full markdown bodies, frontmatter metadata, companion `scripts/`, `references/`, and `assets/` intact, while dotai-specific provenance and trigger metadata are recorded alongside in `.dotai-metadata.json`. New installs are security-vetted before use.

```bash
# Install from a GitHub repo — preserves native SKILL.md packages intact
dotai install https://github.com/slavingia/skills

# Install a specific skill from a repo
dotai install https://github.com/user/ai-skills -s deploy

# Install from a local directory
dotai install ~/my-skills/review

# Install to a specific project instead of global
dotai install https://github.com/team/skills -p my-project
```

Installed skills are immediately available to `dotai context` and configured
agent adapters.

Refresh skills that were installed from a tracked source (team conventions repo):

```bash
dotai install --update
dotai install --update -s mvp
```

Updates are staged and security-vetted before installation. A blocked or declined update leaves the existing skill unchanged. Multi-skill repositories refresh each recorded skill independently. `--skip-vet` is an explicit trust override and should only be used for a source you have reviewed.

### Installing other skill formats

`dotai install` detects dotai skills, native `SKILL.md` packages, Claude
plugins, Cursor plugins, and Gemini extensions, preserving full instruction bodies and companion resources:

```bash
dotai install /path/to/SKILL.md
dotai install /path/to/claude-plugin/
dotai install /path/to/cursor-plugin/
dotai install /path/to/gemini-extension/
```

Supported plugin formats:
- **Claude plugins** — directories with `.claude-plugin/plugin.json`
- **Cursor plugins** — directories with `.cursor-plugin/plugin.json`
- **Gemini extensions** — directories with `gemini-extension.json`

Hooks, tool permissions, and MCP server configurations remain harness-specific and are not claimed as portable execution semantics.

### Removing skills

```bash
# Remove a skill by name (will ask for confirmation)
dotai remove mvp

# Remove without confirmation
dotai remove mvp --force

# Remove from a specific project
dotai remove mvp -p my-project
```

### Tracking sources

Installed skills remember where they came from. Use `dotai skills` to see the source column:

```bash
dotai skills
# Shows: Name, Trigger, Category, Scope, Source, Description
# Source shows "slavingia/skills" for GitHub imports, path for local installs
```

## Creating Skills

```bash
# Simple single-file skill
dotai new-skill "Deploy" -t /run_deploy -c deployment

# Native folder-based SKILL.md package with scripts and assets
dotai new-skill "Deploy" -t /run_deploy -c deployment --folder
```

## CLI Reference

```bash
dotai init [project-path]              # Initialize ~/.ai/ or project .ai/
dotai roles                            # List legacy roles (transitional)
dotai migrate [--dry-run] [-p project] # Losslessly migrate legacy skills and roles
dotai skills [-c category]             # List skills (optionally filter by category)
dotai sync [path] [--check]            # Refresh safe local context
dotai agent setup|status|last|remove claude [--apply]  # User-level Claude delivery
dotai insights [--agent name] [-p project] [--json]  # Local selection & delivery receipts
dotai primer [--project <name>|--path <path>]  # Compact generic bootstrap
dotai context --path <path> [--task ...] [--files ...] [--context ...] [--domain ...] [--skill ...]
dotai rules [-p project] [-a] [--check]    # List rules (or audit quality)
dotai audit [-p project] [--json] [--fail-on severity]  # Read-only rule audit
dotai compress [-p project] [--json]       # Plan compression candidates
dotai compress apply <proposal.json> [--yes]  # Validate, back up, and apply proposals
dotai toggle <rule-id> --on/--off      # Enable/disable rules globally or per-project
dotai learn "title" --directive "..."    # Teach a standard, taste, or guardrail
dotai learn "title" -i "..." -c "..."  # Preserve a correction as a rule
dotai learn "title" -i "..." -c "..." --dry-run|--sync|--force
dotai learn "title" --from-file <f>    # Import structured rule from a file
dotai import-agent <path> [-m mode] [--dry-run]  # Non-destructive agent-file migration
dotai prefs [list|show|new|pull|use|unuse|remove]  # Preference / taste packs
dotai prefs new "CLI" --domain cli     # Create a soft style pack
dotai prefs pull <path|url> [-n id]    # Borrow / install a pack
dotai prefs use <id> [-p project|--global]  # Activate pack in an explicit scope
dotai install <source> [-s skill]      # Install skills from git repo or local path
dotai install --update [-s skill] [--skip-vet]  # Vetted refresh from recorded sources
dotai remove <skill> [-p project]     # Remove an installed skill
dotai new-skill <name> [-t trigger]    # Create a new skill from template
dotai search "query" [--type t] [--tag] [--path .] # Search knowledge for a directory
```

## Philosophy & Product Focus

As coding models and native agent harnesses improved, generic workflow libraries, persona catalogs, implicit keyword routing, and prompt-based "careful mode" wrappers became redundant overhead. Beginning in `0.8.0` (see [`PRODUCT.md`](./PRODUCT.md)), dotai focuses strictly on **durable personal developer guidance**—the private standards, local constraints, architectural decisions, and exceptions that a better model cannot infer on its own:

- **Focused on private guidance** — Captures what is specific to you and your repositories; leaves generic competence, session compaction, and permission sandboxing to your harness.
- **Native-first** — Uses canonical `SKILL.md` packages with scripts, references, and assets intact instead of lossy intermediate formats.
- **Explicit & deterministic** — File scopes, tags, preference domains, and explicit `--skill` selection rather than opaque keyword guessing.
- **File-based & local** — Readable, versionable Markdown files in `~/.ai/` with no server or account.

## License

MIT — see [LICENSE](./LICENSE).
