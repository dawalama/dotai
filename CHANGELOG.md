# Changelog

## 0.9.0 — 2026-11-25

### Added

- **Native multi-agent projection (`dotai agent setup <claude|codex|gemini|agents|all> --apply`)**:
  Compiles `~/.ai/` rules, freeform notes, active general preferences, and native `SKILL.md`
  packages directly into each harness's native user-level config directories—eliminating
  mid-conversation CLI tool calls and preserving prompt caching:
  - `claude`: projects `~/.claude/rules/dotai-*.md` with native `paths:` YAML frontmatter for
    file-scoped rules, prunes stale managed files, and symlinks `SKILL.md` packages into
    `~/.claude/skills/`.
  - `codex`, `gemini`, `agents`: projects marker-managed blocks into `~/.codex/AGENTS.md`,
    `~/.gemini/GEMINI.md`, and `~/.agents/AGENTS.md` plus `~/.agents/skills/` symlinks.
- **Auto-memory harvesting (`dotai harvest claude`)**: Read-only scanner for Claude Code's
  `~/.claude/projects/*/memory/*.md` silos that filters out index links and already-covered
  rules, with `--promote <N> [--dry-run]` to explicitly promote durable lessons into `~/.ai/rules/`.
- **Compliance, dead-glob, budget, and team-conflict auditing (`dotai audit --path .`)**:
  Adds deterministic checks for `conditional-wording`, `rule-budget`, `dead-glob` (globs
  matching zero files in a repo), and `team-conflict` / `team-overlap` against repository
  `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `.claude/rules/*.md`, `.cursor/rules/*.mdc`, and
  `.github/copilot-instructions.md`.
- **Repository trust gate (`dotai trust`)**: Adds `trusted_paths` and `require_trust`
  (`--strict on|off`) to protect against instruction-file poisoning in untrusted repositories.

### Changed

- `dotai agent` defaults to `--mode native` across `claude`, `codex`, `gemini`, `agents`, and
  `all`. Legacy Claude CLI self-invocation remains accessible via `--mode cli-bootstrap`.
- `dotai init` no longer scaffolds legacy `tools/` directories or advertises `tools/` in primers.
- `dotai.tools.registry.load_tools_from_file` now refuses to execute arbitrary Python modules
  unless `allow_exec=True` is explicitly passed.

## 0.8.0 — 2026-11-07

### Product focus decision

- Narrowed dotai around **durable personal developer guidance**—private standards,
  architectural decisions, local constraints, exceptions, and lessons deliberately
  retained across repositories and coding agents. Retired features that merely
  duplicated ordinary engineering competence or native harness capabilities.

### Added

- `dotai migrate`: Losslessly migrates legacy folder skills (`main.md` -> `SKILL.md`)
  and legacy persona roles to user-authored perspective skills with safety backups
  under `~/.config/dotai/backups/`. Supports `--dry-run` to preview actions.

### Changed

- **Native skill packages**: Adopt canonical `SKILL.md` packages with package bodies,
  metadata, scripts, references, assets, and relative paths kept intact. Removed
  lossy section slicing from skill converters. Dotai-specific metadata is stored
  cleanly in `.dotai-metadata.json`.
- **Durable personal guidance focus**: Fresh initialization (`dotai init`) creates
  empty starter structures and `rules.md` without bundling mandatory generic
  workflow or persona libraries. Existing user files are preserved during upgrade.
- **Explicit workflow selection**: Removed implicit task-word routing (`_route_skill`).
  Incidental words in tasks do not trigger workflows; skills load only when
  explicitly requested (`--skill`).
- **Retired automatic persona injection**: Roles are deprecated as a first-class
  abstraction; perspective guidance is maintained as standard user-authored skills.
  Legacy roles remain readable for backward compatibility and can be migrated.
- **Claude bootstrap reassessment**: Avoid unconditional repeated resolver calls
  when no file-scoped guidance exists or task state has not changed.
- **Accurate product claims**: Receipt reporting and documentation distinguish
  selection from agent compliance or causality ("what dotai selected and returned,
  and why"), distinguish Claude Code's automatic user-memory adapter from portable
  manual CLI resolution, and state clearly that prompt rules are guidance rather
  than enforced sandbox boundaries.

### Removed

- Bundled generic seed workflows (`src/dotai/seed/skills/*`, including prompt-based
  careful mode and session-bootstrap context dumps) and generic seed roles
  (`src/dotai/seed/roles/*`) from default installation. Existing user-installed
  files in `~/.ai/` and project `.ai/` directories are never deleted.

## 0.7.1 — 2026-11-06

### Fixed

- `sync_project` no longer deletes `CLAUDE.md` content after a `# AI Context`
  substring. A legacy generated block is replaced only when the heading is a
  whole line, the next content is the old primer, and the block ends at a
  closing sentence dotai used to write. Text outside that span stays. Any other
  heading is left in place and the managed block is appended.

## 0.7.0 — 2026-11-04

### Changed

- Share project discovery and override handling between context resolution and
  primers, including nested directories, custom knowledge paths, and disabled
  local overrides. Unrelated registered projects are excluded.
- Deliver full universal rule bodies and freeform conventions in resolved
  context. Compact primers replace individual scoped-rule listings with a count
  and resolver pointer.
- Load active general preferences by default, advertise other active domains,
  and honor explicitly requested packs independently of domain selection.
- Preserve complete bodies when loading existing dotai skills while retaining
  structured Python fields and identifying the source directory.
- Report file-scope facts separately from resolution status; missing files keep
  a resolution provisional whenever scoped rules exist.

### Fixed

- Match inherited rule globs from nested working directories and preserve hidden
  and symlinked file names during matching.
- Avoid receipt temporary-file collisions and tolerate concurrent history
  pruning at the retention limit.
- Pluralize the compact primer's file-scoped rule count.
- Treat a rule as universal only when every glob is a catch-all, so one
  specific glob keeps the rule file-scoped.
- Search, `rules`, project audits, scoped insights, and project skill sync
  read the same ancestor catalog as context. Unrelated projects stay out.

## 0.6.0 — 2026-07-17

### Added

- `dotai learn --directive` for proactive engineering standards, taste, and
  guardrails without requiring a prior mistake.
- `dotai insights` for deterministic local delivery evidence: resolution health,
  selection counts, last use, rule-summary exposure, and unused knowledge.
- Bounded metadata-only receipt history, retaining the latest 500 resolutions
  per agent.
- `PRODUCT.md` defining dotai as portable engineering judgment for coding agents.

### Changed

- Repositioned the CLI and documentation around developer-controlled engineering
  judgment rather than universal context.
- `dotai sync` now has one repository-safe behavior: local context outside the
  worktree.
- `dotai primer` now always emits the compact bootstrap.
- `dotai search` reads live knowledge instead of a cached index.
- `dotai install` is the single entry point for supported external skill formats.

### Removed

- Commands: `watch`, `detach`, `index`, `tree`, `prompt`, `role`, `convert`, and
  `import-plugin`.
- Shared/full/agent-specific sync controls and primer session overlays.
- Freeform `dotai learn --append-md` capture.
- The cached knowledge-tree model and `watchdog` dependency.

This release intentionally breaks pre-1.0 CLI compatibility to keep one clear,
local-first product path.
