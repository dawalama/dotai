# Changelog

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
