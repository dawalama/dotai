# Changelog

## Unreleased

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
