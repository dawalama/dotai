# dotai

**Portable engineering judgment for coding agents.**

dotai teaches Claude, Cursor, Gemini, Codex, and other coding agents how you build software. Keep your standards, workflows, guardrails, and engineering taste in `~/.ai/`; dotai applies only the judgment each task needs without taking ownership of team files.

```text
~/.ai/ ── dotai context ── relevant rules + skill + role + preferences
   │
   └──── dotai sync ────── local context cache (outside Git repositories)
```

Teach it once. Apply it when relevant. Know what influenced the agent. No server, account, or proprietary memory layer—just portable Markdown that you own.

## The short version

| You want to… | Use |
|---|---|
| Teach agents a standard, taste, or guardrail | `dotai learn --directive` |
| Use dotai automatically in Claude Code | `dotai agent setup claude --apply` |
| See what Claude actually loaded | `dotai agent last claude` |
| Resolve context manually or from automation | `dotai context` |
| Prepare a safe per-repository cache | `dotai sync` |

The default is personal and repository-safe. Team instructions stay authoritative.

## Make every agent work like yours

You prefer derived state over synchronization effects. You reproduce bugs before fixing them. You never allow credentials in logs. These are different kinds of judgment, but they all shape how you build software—and they should not disappear when you change agents.

dotai turns that judgment into durable, reusable instructions:

- **Rules codify decisions.** Capture standards, architectural taste, safety boundaries, and compliance requirements; scope them by project or file pattern.
- **Skills are repeatable workflows.** Plan, investigate, review, verify, and ship the same way every time.
- **Roles change how the agent thinks.** Review as a security engineer; plan as a product manager.
- **Preference packs carry your taste.** Share softer choices without weakening hard rules.
- **Adapters fit normal workflows.** Configure an agent once, then ask naturally while dotai resolves context behind the scenes.

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

# Teach every agent an engineering preference
dotai learn "no-useeffect" \
  --directive "Never call useEffect directly; prefer declarative alternatives" \
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

Then ask naturally. dotai routes unambiguous workflows and expands matching file-scoped rules:

```text
Plan this feature as a product manager.
Investigate this failure.
Review the authentication changes.
Verify the pending changes.
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
dotai roles
dotai skills
dotai rules

# Prepare agent context for a project
cd ~/my-project
dotai sync
```

`dotai sync` always writes personal context under `~/.config/dotai/contexts/` and leaves team-owned files such as `CLAUDE.md`, `AGENTS.md`, and `.claude/skills/` untouched. Existing repository instructions are copied into the local context as the authoritative layer; personal dotai rules and preferences are explicitly supplemental.

Local context storage does not, by itself, make an agent load the context. Until an agent adapter is configured, use `dotai primer --path .` to print a compact bootstrap for pasting or piping into your agent.

dotai uses progressive disclosure to keep prompts small. Synced context contains rule summaries and role/skill catalogs. Expand only what a task needs:

```bash
# Expand rules matching the affected files
dotai context --path . --files src/api.py,tests/test_api.py

# Expand security-tagged rules and an active CLI preference pack
dotai context --path . --context security --domain cli

# Load one complete skill and its declared role
dotai context --path . --skill run_review
```

Selection is deterministic: file globs, explicit context tags, active preference domains, and named skills or roles. dotai does not guess from semantic similarity. Every expanded item includes the reason it was selected.

### Automatic delivery with Claude Code

The resolver is infrastructure; you should not have to type `dotai context`
during normal work. Install dotai's user-level Claude adapter once:

```bash
# Preview the user-memory change
dotai agent setup claude

# Back up existing memory and install it
dotai agent setup claude --apply

# Confirm activation
dotai agent status claude

# See the most recent context Claude actually resolved
dotai agent last claude
```

The adapter adds a small marker-managed block to `~/.claude/CLAUDE.md`, which
Claude Code loads as user memory across projects. It tells Claude to resolve
dotai context for substantial development work, after affected files are known,
and to avoid repeated calls when the task has not changed. Repository and
organization instructions remain authoritative.

For file-sensitive workflows such as review, debugging, verification, scaffolding,
maintenance, and release work, a resolution without `--files` is explicitly
marked provisional. Claude must resolve again after discovering the affected
files. `dotai agent last claude` reports whether the latest resolution is
`provisional` or `complete`.

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

### Understanding what dotai delivered

`dotai insights` aggregates local resolution receipts so you can see whether
your engineering judgment is actually being selected:

```bash
dotai insights
dotai insights --agent claude
dotai insights --project my-app
dotai insights --json
```

The report shows complete versus provisional resolutions, selection counts,
last-selected timestamps, universal rule-summary exposure, and enabled items
that have never been selected in the current window. Selection proves delivery,
not compliance: dotai cannot claim that an agent followed an instruction merely
because it received it.

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

# Print the context for an agent that does not yet have a dotai adapter
dotai primer --path .
```

With the Claude adapter installed, daily use is simpler: open Claude Code and
ask for the work normally. Claude invokes the pinned dotai executable, resolves
the workflow, and resolves again with affected files when file-scoped rules may
apply. Use `dotai agent last claude` whenever you want to verify delivery.

### Using skills in Claude Code

Natural-language routing is recommended with the personal adapter:

```
> /run_plan                            # Plan before coding
> /run_plan as product-manager         # Scope with acceptance criteria
> /run_plan as systems-architect       # Architecture deep-dive
> /run_review                          # Review current branch diff
> /run_review as security-engineer     # Security-focused audit
> /run_ship                            # Sync, test, push, create PR
> /run_techdebt                        # Scan for tech debt
> /run_careful                         # Enter production-safety mode
> /run_verify                          # Run tests, types, lint, build
> /run_learn                           # Capture a mistake as a permanent rule
> /run_compress                        # Draft and review smaller rule definitions
```

### Using skills outside Claude Code

Resolve a skill and its role through the same context engine used by adapters:

```bash
dotai context --path . --skill run_review --role paranoid-reviewer

# List skills filtered by category
dotai skills --category deployment
```

### Teaching your engineering judgment

`dotai learn` creates a **structured rule file** in `~/.ai/rules/` by default. Use a directive for a standard you already hold; use an issue and correction when an agent interaction teaches you something new.

```bash
# Proactively encode engineering taste or a guardrail
dotai learn "no-useeffect" \
  --directive "Never call useEffect directly; prefer declarative alternatives" \
  --globs "*.tsx,*.ts"

# Preview the rule without writing
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
dotai learn "no-useEffect" --from-file react-rules.md --globs "*.tsx,*.ts"

# Or ask an adapted agent naturally
> Capture what we learned as a rule.

# Disable a rule for one legacy project
dotai toggle no-useeffect --off --project legacy-app

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

`dotai compress` turns high-confidence findings into a conservative plan. Semantic rewriting is handled by the active coding agent, not a hidden provider inside the CLI:

```bash
# Inspect candidates
dotai compress

# Ask an adapted coding agent to use the compression workflow
> Compress and audit my dotai rules.

# Low-level application boundary for an approved versioned proposal
dotai compress apply proposal.json
```

The compression skill reads the JSON plan, drafts shorter complete rules, explains what it preserved and consolidated, shows the full diff in conversation, and asks `Apply this compression? [y/N]`. It then passes only approved changes to dotai. Near-duplicates, generic guidance, and rules that may belong in a preference pack remain suggestions unless the developer explicitly approves a concrete proposal.

When no exact duplicates exist, compression says there are no **safe automatic** savings while still listing semantic review candidates and their estimated savings. These estimates are directional—they help prioritize review. The CLI never invents a semantic rewrite or calls an external provider.

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

```bash
# Search by keyword
dotai search "useEffect"

# Filter by type
dotai search "review" --type skill

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

# Each project can have its own rules, roles, and skills in .ai/
# Project-level rules override global ones during sync
```

## Directory Structure

```
~/.ai/                          # Global (cross-project)
├── rules.md                    # Inline rules, conventions, and lessons learned
├── rules/                      # Structured rules (hard constraints)
│   └── no-useeffect.md         # Example: ban useEffect in React
├── preferences/                # Soft taste packs (borrowable style priors)
│   └── cli.md                  # Example: CLI stack / micro-style
├── preferences-active.json     # Which preference packs are active
├── backups/                    # Local snapshots created before compression writes
├── roles/                      # Cognitive modes
│   ├── reviewer.md             # Paranoid staff engineer
│   ├── architect.md            # Systems thinker
│   ├── qa.md                   # Methodical tester
│   ├── founder.md              # Product visionary
│   ├── ship.md                 # Release engineer
│   ├── writer.md               # Documentation specialist
│   ├── debugger.md             # Root cause analyst
│   ├── security.md             # Application security specialist
│   ├── mentor.md               # Patient teacher and pair programmer
│   └── product-manager.md      # Scoping, acceptance criteria, prioritization
├── skills/                     # Reusable workflows
│   ├── review.md               # Code review (/run_review)
│   ├── commit-helper.md        # Conventional commit messages (/run_commit)
│   ├── context-dump.md         # Context dump for new sessions (/run_context)
│   ├── parallel-work.md        # Git worktree parallel dev (/run_parallel)
│   ├── ship.md                 # Sync, test, push, PR (/run_ship)
│   ├── techdebt.md             # Find tech debt (/run_techdebt)
│   ├── careful.md              # Production-safety mode (/run_careful)
│   ├── investigate.md          # Root-cause analysis (/run_investigate)
│   ├── scaffold.md             # Boilerplate generation (/run_scaffold)
│   ├── verify.md               # Run tests, types, lint (/run_verify)
│   ├── plan.md                 # Structured planning workflow (/run_plan)
│   ├── learn.md                # Capture learnings as rules (/run_learn)
│   ├── compress.md             # Review semantic rule compression (/run_compress)
│   └── deploy/                 # Folder-based skill (with scripts & assets)
│       ├── main.md
│       ├── scripts/
│       ├── assets/
│       └── config.json
└── tools/                      # Python tool implementations
    └── *.py

<project>/.ai/                  # Per-project overrides
├── rules.md                    # Project-specific rules and conventions
├── rules/                      # Project-specific structured rules
├── roles/                      # Project-specific roles
├── skills/                     # Project-specific skills
└── tools/                      # Project-specific tools
```

## Skills

Skills are reusable AI workflows organized into **9 categories**:

| Category | Purpose | Example |
|----------|---------|---------|
| `reference` | Library/CLI documentation lookups | API docs, framework guides |
| `verification` | Testing, validation, type-checking | Test runners, lint checks |
| `data` | Dashboards, queries, monitoring | Query templates |
| `workflow` | Multi-step automation | `/run_parallel`, `/run_context` |
| `scaffolding` | Boilerplate / code generation | Project templates |
| `code-quality` | Review, linting, style enforcement | `/run_review`, `/run_techdebt` |
| `deployment` | CI/CD, release, ship | `/run_ship` |
| `debugging` | Investigation, root-cause analysis | Root-cause workflows |
| `maintenance` | Operational procedures, migrations | Runbook skills |

### Skill Triggers

All skill triggers use the `run_` prefix to avoid collisions with built-in agent commands:

| Skill | Trigger | Description |
|-------|---------|-------------|
| Code Review | `/run_review` | Diff-based structural review |
| Commit Helper | `/run_commit` | Conventional commit messages |
| Context Dump | `/run_context` | Session context for onboarding |
| Parallel Work | `/run_parallel` | Git worktree management |
| Ship | `/run_ship` | Sync, test, push, create PR |
| Find Tech Debt | `/run_techdebt` | Identify debt and duplication |
| Careful Mode | `/run_careful` | Production-safety guardrails |
| Investigate | `/run_investigate` | Systematic root-cause analysis |
| Scaffold | `/run_scaffold` | Generate boilerplate from patterns |
| Verify | `/run_verify` | Run tests, types, lint, build |
| Plan | `/run_plan` | Structured planning before coding |
| Learn | `/run_learn` | Capture engineering judgment as structured rules |

### Skill Format

Skills support both **structured** and **runbook** formats:

```markdown
---
name: Code Review
trigger: /run_review
role: reviewer
category: code-quality
allowed-tools: Read, Grep, Glob, Bash
context: local, ci
tags: review, quality
---

Analyze the current branch's diff for issues that tests don't catch.

## Gotchas

- Large diffs (>500 lines) should be split into per-file reviews
- Always verify the base branch before diffing

## Steps

1. Detect the base branch
2. Read the full diff
3. Check for security issues, error swallowing, race conditions
4. Generate a structured report with file:line references
```

### Gotchas

Skills should document **common failure points** — things that push the agent out of its normal way of thinking. Gotchas are rendered with warning markers in the agent prompt so they get extra attention.

### Conditional Contexts

Skills can specify which contexts they're active in:

```yaml
context: production, sensitive
```

This lets you create production-safety skills that activate extra caution for operations affecting live systems.

### Folder-Based Skills

For complex workflows, skills can be directories with helper scripts and assets:

```
~/.ai/skills/deploy/
├── main.md          # Skill definition (frontmatter + body)
├── scripts/         # Shell/Python scripts the agent can invoke
│   ├── health-check.sh
│   └── rollback.py
├── assets/          # Templates, reference docs, configs
│   └── pr-template.md
└── config.json      # User-specific configuration
```

Folder-based skills enable **progressive disclosure** — the agent reads `main.md` for the workflow, then pulls in scripts only when needed. This keeps token usage efficient.

## Roles

A role is a cognitive mode — a persona that frames how the AI approaches a task.

### Role Format

```markdown
---
name: Paranoid Reviewer
description: Staff engineer focused on production safety
tags: review, security, quality
---

You are a paranoid staff engineer reviewing code before it lands in production.
Your job is to find bugs that tests don't catch...

## Principles
- Assume every external input is hostile
- Check error paths, not just the happy path

## Anti-patterns
- Commenting on style — that's the linter's job
```

Skills reference roles by ID — when a skill runs, the role's full persona is injected into the prompt.

### Composing Skills with Roles

Ask for a perspective naturally through an adapter, or resolve it explicitly
with `dotai context --skill <skill> --role <role>`.

```
/run_plan as product-manager         # Scope a feature with acceptance criteria
/run_plan as systems-architect      # Architecture deep-dive with tradeoffs
/run_review as paranoid-reviewer    # Security-focused code review
/run_review as security-engineer    # Full OWASP-style security audit
/run_techdebt as debugger           # Hunt tech debt with a debugger's mindset
/run_review as mentor               # Review that teaches, not just critiques
/run_review                         # Uses the skill's default role, or none
```

The resolver expands the role and skill together and records why each was selected.

## Rules

Rules are structured coding standards that agents enforce automatically.

### Structured Rules

Individual rule files live in `~/.ai/rules/` with frontmatter:

```markdown
---
name: no-useEffect
description: Never call useEffect directly
globs: "*.tsx, *.ts"
tags: react, hooks
enabled: true
---

All useEffect usage must be replaced with declarative patterns...
```

### Managing Rules

```bash
# List active rules
dotai rules

# Audit duplicates / empty bodies
dotai rules --check

# Import a rule from an external file
dotai learn "no-useEffect" --from-file react-rule.md --globs "*.tsx,*.ts"

# Record a learning as a structured rule (default)
dotai learn "auth-header" --issue "Forgot Bearer prefix" --correction "Always prepend Bearer to tokens"

# Preview first
dotai learn "auth-header" -i "..." -c "..." --dry-run

# Disable a rule globally
dotai toggle no-useeffect --off

# Disable a rule for a specific project only
dotai toggle no-useeffect --off --project my-legacy-app

# Re-enable
dotai toggle no-useeffect --on
```

Synced local context contains a compact bootstrap: universal rule summaries plus preference, role, and skill catalogs. Use `dotai context` to expand relevant material on demand.

## Agent Sync

`dotai sync` prepares repository-safe local context with:

- **Universal structured rule summaries** (always visible)
- **Pointers to freeform `rules.md` conventions**
- **Role and skill catalogs** (names, triggers, categories — not full workflows)
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
dotai context --path . --skill run_review
```

Use an agent adapter for automatic delivery. For an agent without an adapter,
paste or pipe `dotai primer --path .`, then use `dotai context` for task-specific
expansion.

## Installing Skills

Install skills from git repos or local directories. Claude-native `SKILL.md` files are auto-detected and converted to dotai format with triggers and categories inferred from the content. New installs are security-vetted before use.

```bash
# Install from a GitHub repo — auto-detects and converts Claude-native skills
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

`dotai install` detects dotai skills, Claude-native `SKILL.md` files, Claude
plugins, Cursor plugins, and Gemini extensions. Supported skills and commands
are converted automatically:

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

Hooks and MCP server configurations remain tool-specific and are not installed.

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
# Shows: Name, Trigger, Category, Role, Scope, Source, Description
# Source shows "slavingia/skills" for GitHub imports, path for local installs
```

## Creating Skills

```bash
# Simple single-file skill
dotai new-skill "Deploy" -t /run_deploy -c deployment

# Folder-based skill with scripts and assets
dotai new-skill "Deploy" -t /run_deploy -c deployment --folder
```

## CLI Reference

```bash
dotai init [project-path]              # Initialize ~/.ai/ or project .ai/
dotai roles                            # List available roles
dotai skills [-c category]             # List skills (optionally filter by category)
dotai sync [path] [--check]            # Refresh safe local context
dotai agent setup|status|last|remove claude [--apply]  # User-level Claude delivery
dotai insights [--agent name] [-p project] [--json]  # Local delivery evidence
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
dotai search "query" [--type t] [--tag] # Search live knowledge
```

## Philosophy

- **Model-agnostic** — Works with Claude, Cursor, Gemini, Codex, Copilot, Ollama, or any LLM
- **File-based** — No databases, no servers, just markdown files in `~/.ai/`
- **Composable** — Roles are reusable across skills, skills across projects
- **Portable** — Your knowledge travels with you, not locked into one tool
- **Gotcha-first** — Skills document failure points, not just happy paths
- **Progressive disclosure** — Folder-based skills keep token usage efficient

## License

MIT — see [LICENSE](./LICENSE).
