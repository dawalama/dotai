# dotai

Universal AI context for any coding agent. Roles, skills, and rules in `~/.ai/`.

## The Problem

Every AI coding tool has its own way to store context:

- Claude Code → `CLAUDE.md`
- Cursor → `.cursorrules`
- Gemini CLI → `GEMINI.md`
- Codex / Copilot → `AGENTS.md`

Your knowledge about how to write code, review it, ship it, and debug it gets scattered across tool-specific formats — or worse, stays in your head.

## The Solution

`dotai` defines a universal `~/.ai/` directory convention that any tool can consume. It ships with:

- **Roles** — Cognitive modes that shift how the AI thinks (reviewer, architect, founder, QA, etc.)
- **Skills** — Reusable workflows with steps, inputs, gotchas, and role references
- **Rules** — Structured coding standards with per-project toggles and file-pattern scoping
- **Agent sync** — Generate `CLAUDE.md`, `.cursorrules`, `GEMINI.md`, or `AGENTS.md` from your `~/.ai/`
- **Native slash commands** — For Claude Code, skills become real `/run_*` commands automatically

## Quick Start

```bash
pip install dotai

# Initialize ~/.ai/ with seed roles and skills
dotai init

# See what's available
dotai roles
dotai skills
dotai rules

# Sync agent bootstrap files into a project
cd ~/my-project
dotai sync
```

This generates agent config files in your project root — `CLAUDE.md`, `.cursorrules`, `GEMINI.md`, and `AGENTS.md` — each with your complete knowledge context inline. For Claude Code, it also generates `.claude/skills/` entries so your skills appear as native slash commands.

## Usage

### Daily workflow

```bash
# Start of day: sync your knowledge into the project you're working on
cd ~/my-project
dotai sync

# Now open your editor — Claude Code, Cursor, Gemini, etc.
# Your roles, skills, and rules are already loaded.
```

### Using skills in Claude Code

After `dotai sync`, skills appear as native slash commands:

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
```

### Using skills outside Claude Code

Assemble a skill prompt and pipe it into any tool:

```bash
# Copy a skill prompt to clipboard
dotai prompt review --role paranoid-reviewer | pbcopy

# Save to a file
dotai prompt ship > /tmp/ship-prompt.md

# List skills filtered by category
dotai skills --category deployment
```

### Recording what you learn

```bash
# Something went wrong — record it so the AI never repeats it
dotai learn "auth-header" \
  --issue "Forgot Bearer prefix on API token" \
  --correction "Always prepend 'Bearer ' to auth tokens"

# Import a detailed rule from a file
dotai learn "no-useEffect" --from-file react-rules.md --globs "*.tsx,*.ts"

# Disable a rule for one legacy project
dotai toggle no-useeffect --off --project legacy-app
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
├── rules/                      # Structured rules (individual files)
│   └── no-useeffect.md         # Example: ban useEffect in React
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

Skills and roles can be composed inline. Pass `as <role>` to run any skill with a specific persona:

```
/run_plan as product-manager         # Scope a feature with acceptance criteria
/run_plan as systems-architect      # Architecture deep-dive with tradeoffs
/run_review as paranoid-reviewer    # Security-focused code review
/run_review as security-engineer    # Full OWASP-style security audit
/run_techdebt as debugger           # Hunt tech debt with a debugger's mindset
/run_review as mentor               # Review that teaches, not just critiques
/run_review                         # Uses the skill's default role, or none
```

From the CLI:

```bash
dotai prompt review --role paranoid-reviewer | pbcopy
dotai prompt review --role qa > /tmp/prompt.md
```

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

# Import a rule from an external file
dotai learn "no-useEffect" --from-file react-rule.md --globs "*.tsx,*.ts"

# Record an inline learning
dotai learn "auth-header" --issue "Forgot Bearer prefix" --correction "Always prepend Bearer to tokens"

# Disable a rule globally
dotai toggle no-useeffect --off

# Disable a rule for a specific project only
dotai toggle no-useeffect --off --project my-legacy-app

# Re-enable
dotai toggle no-useeffect --on
```

Rules are included inline in every synced agent file, so agents that can't read external files still get the full rule content.

## Agent Sync

`dotai sync` generates tool-specific bootstrap files with **full inline content** — every rule body, role persona, skill definition, and gotcha is embedded so agents that can't read external files still get everything.

```bash
# Generate all (CLAUDE.md + .cursorrules + GEMINI.md + AGENTS.md)
dotai sync

# Generate for specific agents
dotai sync --agents claude,cursor
dotai sync --agents gemini

# Print primer to stdout (for piping)
dotai primer
```

### Supported Agents

| Agent | Output File | Sync Command | Notes |
|-------|-------------|--------------|-------|
| Claude Code | `CLAUDE.md` + `.claude/skills/` | `dotai sync --agents claude` | Marker-based merging + native slash commands |
| Cursor | `.cursorrules` | `dotai sync --agents cursor` | Full context inline |
| Gemini CLI | `GEMINI.md` | `dotai sync --agents gemini` | Auto-discovered in project root and `~/.gemini/GEMINI.md` |
| Generic | `AGENTS.md` | `dotai sync --agents generic` | Works with Codex, Copilot, and any agent that reads it |

For Claude Code, `dotai sync` also generates `.claude/skills/<trigger>/SKILL.md` files. These register as native slash commands — they appear in autocomplete and work as real `/run_*` commands with role composition support built in.

> **Tip:** Run `dotai primer | pbcopy` to copy the full context to your clipboard for pasting into any agent's system prompt.

## Installing Skills

Install skills from git repos or local directories:

```bash
# From a git repository
dotai install https://github.com/user/ai-skills
dotai install https://github.com/user/ai-skills -s deploy

# From a local directory
dotai install ~/my-skills/review

# Install to a specific project
dotai install https://github.com/team/skills -p my-project
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
dotai role <name>                      # Output a role's full prompt to stdout
dotai skills [-c category]             # List skills (optionally filter by category)
dotai prompt <skill> [--role <role>]   # Assemble skill + role prompt for any agent
dotai sync [path] [--agents ...]       # Sync ~/.ai/ into agent config files
dotai primer [--project <name>]        # Print full agent context to stdout
dotai rules [-p project] [-a]          # List rules (resolved or all)
dotai toggle <rule-id> --on/--off      # Enable/disable rules globally or per-project
dotai learn "title" --from-file <f>    # Import structured rule from a file
dotai learn "title" -i "..." -c "..."  # Record an inline learning
dotai install <source> [-s skill]      # Install skills from git repo or local path
dotai new-skill <name> [-t trigger]    # Create a new skill from template
dotai search "query" [--type t] [--tag] # Search knowledge index
dotai index [--refresh]                # Build/show knowledge index
dotai tree                             # Show knowledge tree
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
