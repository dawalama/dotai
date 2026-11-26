"""Compile and project ~/.ai/ personal guidance into native user-level agent surfaces.

Instead of asking coding agents to shell out to a CLI mid-conversation (which burns
turns, breaks prompt caching, and depends on conditional instruction compliance),
projection compiles ~/.ai/ rules, notes, preferences, and SKILL.md packages into each
harness's native user-level configuration directories:

  - claude: ~/.claude/rules/dotai-*.md (with native `paths:` frontmatter) + ~/.claude/skills/
  - codex:  ~/.codex/AGENTS.md (marker-managed block) + ~/.agents/skills/
  - gemini: ~/.gemini/GEMINI.md (marker-managed block) + ~/.agents/skills/
  - agents: ~/.agents/AGENTS.md (marker-managed block) + ~/.agents/skills/
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from .catalog import load_catalog
from .models import GlobalConfig, PreferencePack, Rule, Skill

SUPPORTED_TARGETS = ("claude", "codex", "gemini", "agents")
_SHARED_SKILLS_TARGETS = ("codex", "gemini", "agents")
TargetName = Literal["claude", "codex", "gemini", "agents"]

MANAGED_RULE_MARKER = "<!-- dotai:managed:"
PROJECTED_START_FMT = "<!-- dotai:projected:{target}:start -->"
PROJECTED_END_FMT = "<!-- dotai:projected:{target}:end -->"

TEAM_AUTHORITY_HEADER = (
    "Repository and organization instructions are authoritative. "
    "These personal dotai rules and preferences are supplemental; "
    "ignore any personal instruction that conflicts with team guidance."
)


@dataclass(frozen=True)
class ProjectionOp:
    """One previewable filesystem operation for native projection."""

    action: Literal["create", "update", "remove", "symlink", "unlink_symlink"]
    path: Path
    detail: str
    content: str | None = None
    symlink_target: Path | None = None


@dataclass(frozen=True)
class ProjectionPlan:
    """A complete, previewable native projection plan for one target."""

    target: TargetName
    operations: list[ProjectionOp] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return bool(self.operations)


def _yaml_quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _render_claude_rule(rule: Rule) -> str:
    """Render one dotai Rule as a native Claude Code rule file with optional `paths:`."""
    lines: list[str] = []
    if not rule.is_universal and rule.globs:
        lines.append("---")
        lines.append("paths:")
        for glob in rule.globs:
            lines.append(f"  - {_yaml_quote(glob)}")
        lines.append("---")
        lines.append("")
    lines.append(f"<!-- dotai:managed:rule:{rule.id} -->")
    lines.append(f"# {rule.name}")
    lines.append("")
    lines.append(f"_{TEAM_AUTHORITY_HEADER}_")
    lines.append("")
    if rule.description:
        lines.append(rule.description.strip())
        lines.append("")
    lines.append(rule.body.strip())
    return "\n".join(lines).rstrip() + "\n"


def _render_claude_notes(body: str) -> str:
    lines = [
        "<!-- dotai:managed:notes:global -->",
        "# Personal Conventions (dotai rules.md)",
        "",
        f"_{TEAM_AUTHORITY_HEADER}_",
        "",
        body.strip(),
    ]
    return "\n".join(lines).rstrip() + "\n"


def _render_claude_preferences(packs: list[PreferencePack]) -> str:
    lines = [
        "<!-- dotai:managed:preferences:general -->",
        "# Personal Soft Preferences (dotai)",
        "",
        f"_{TEAM_AUTHORITY_HEADER}_",
        "These are soft style/taste preferences; hard rules and team conventions always win.",
        "",
    ]
    for pack in packs:
        lines.append(pack.to_prompt())
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _render_compiled_agents_block(
    target: TargetName,
    rules: list[Rule],
    notes_body: str,
    general_prefs: list[PreferencePack],
) -> str:
    """Render a compact, cache-friendly markdown block for AGENTS.md / GEMINI.md."""
    start = PROJECTED_START_FMT.format(target=target)
    end = PROJECTED_END_FMT.format(target=target)

    body_lines = [
        "# Personal Engineering Guidance (dotai)",
        "",
        TEAM_AUTHORITY_HEADER,
        "",
    ]

    universal_rules = [r for r in rules if r.is_universal]
    scoped_rules = [r for r in rules if not r.is_universal]

    if universal_rules:
        body_lines.append("## Universal Rules")
        body_lines.append("")
        for rule in universal_rules:
            body_lines.append(rule.to_prompt())
            body_lines.append("")

    if scoped_rules:
        body_lines.append("## File-Scoped Rules")
        body_lines.append("")
        for rule in scoped_rules:
            globs = ", ".join(f"`{g}`" for g in rule.globs)
            body_lines.append(f"### {rule.name} (applies to: {globs})")
            if rule.description:
                body_lines.append(f"_{rule.description}_")
            body_lines.append("")
            body_lines.append(rule.body.strip())
            body_lines.append("")

    if notes_body.strip():
        body_lines.append("## Freeform Conventions")
        body_lines.append("")
        body_lines.append(notes_body.strip())
        body_lines.append("")

    if general_prefs:
        body_lines.append("## Soft Preferences")
        body_lines.append("")
        for pack in general_prefs:
            body_lines.append(pack.to_prompt())
            body_lines.append("")

    inner = "\n".join(body_lines).rstrip()
    return f"{start}\n{inner}\n{end}"


def _validate_projection_markers(content: str, target: TargetName, path: Path) -> bool:
    start = PROJECTED_START_FMT.format(target=target)
    end = PROJECTED_END_FMT.format(target=target)
    has_start = start in content
    has_end = end in content
    if has_start != has_end:
        raise ValueError(f"{path} contains incomplete dotai projection markers")
    if has_start and content.index(start) > content.index(end):
        raise ValueError(f"{path} contains reversed dotai projection markers")
    return has_start


def _remove_projected_block(content: str, target: TargetName) -> tuple[str, bool]:
    start = PROJECTED_START_FMT.format(target=target)
    end = PROJECTED_END_FMT.format(target=target)
    if start not in content or end not in content:
        return content, False
    if content.index(start) > content.index(end):
        return content, False
    before, _, rest = content.partition(start)
    _, _, after = rest.partition(end)
    cleaned = "\n\n".join(
        part for part in (before.rstrip(), after.lstrip().rstrip()) if part
    )
    return (cleaned + "\n" if cleaned else ""), True


def _plan_marker_file_upsert(
    path: Path,
    target: TargetName,
    block: str,
    ops: list[ProjectionOp],
    warnings: list[str],
) -> None:
    if path.is_symlink():
        warnings.append(f"Skipped symlinked instruction file: {path}")
        return
    if not path.exists():
        ops.append(ProjectionOp("create", path, f"create {path.name} with projected dotai guidance", content=block + "\n"))
        return
    existing = path.read_text()
    _validate_projection_markers(existing, target, path)
    cleaned, found = _remove_projected_block(existing, target)
    new_content = f"{cleaned.rstrip()}\n\n{block}\n" if cleaned.strip() else block + "\n"
    if found and new_content == existing:
        return
    detail = f"refresh projected dotai block in {path.name}" if found else f"append projected dotai block to {path.name}"
    ops.append(ProjectionOp("update", path, detail, content=new_content))


def _plan_marker_file_remove(
    path: Path,
    target: TargetName,
    ops: list[ProjectionOp],
    warnings: list[str],
) -> None:
    if not path.exists():
        return
    if path.is_symlink():
        warnings.append(f"Skipped symlinked instruction file: {path}")
        return
    existing = path.read_text()
    _validate_projection_markers(existing, target, path)
    cleaned, found = _remove_projected_block(existing, target)
    if not found:
        return
    if cleaned:
        ops.append(ProjectionOp("update", path, f"remove projected dotai block from {path.name}", content=cleaned))
    else:
        ops.append(ProjectionOp("remove", path, f"remove dotai-only {path.name}"))


def _has_active_projected_block(target: TargetName, home: Path) -> bool:
    inst_path = _target_instruction_path(target, home)
    if not inst_path.exists() or inst_path.is_symlink():
        return False
    try:
        text = inst_path.read_text()
    except OSError:
        return False
    start = PROJECTED_START_FMT.format(target=target)
    end = PROJECTED_END_FMT.format(target=target)
    return start in text and end in text and text.index(start) < text.index(end)


def _is_dotai_managed_skill_symlink(link: Path, global_skills_dir: Path) -> bool:
    if not link.is_symlink():
        return False
    try:
        resolved_target = link.resolve(strict=False)
        return resolved_target.is_relative_to(global_skills_dir.resolve())
    except OSError:
        return False


def _plan_skill_symlinks(
    skills: list[Skill],
    target_skills_dir: Path,
    global_skills_dir: Path,
    ops: list[ProjectionOp],
    warnings: list[str],
) -> None:
    """Project native folder SKILL.md packages via safe symlinks."""
    desired: dict[str, Path] = {}
    for skill in skills:
        if skill.is_folder_skill and skill.assets_dir and (skill.assets_dir / "SKILL.md").is_file():
            desired[skill.id] = skill.assets_dir.resolve()

    for skill_id, src_dir in sorted(desired.items()):
        dest = target_skills_dir / skill_id
        if dest.is_symlink():
            current = dest.resolve(strict=False)
            if current == src_dir:
                continue
            if _is_dotai_managed_skill_symlink(dest, global_skills_dir):
                ops.append(ProjectionOp("unlink_symlink", dest, f"re-link skill {skill_id}"))
                ops.append(ProjectionOp("symlink", dest, f"link skill {skill_id} -> {src_dir}", symlink_target=src_dir))
            else:
                warnings.append(f"Skipped non-dotai symlink at {dest}")
        elif dest.exists():
            warnings.append(f"Skipped existing non-symlink skill directory at {dest}")
        else:
            ops.append(ProjectionOp("symlink", dest, f"link native skill {skill_id}", symlink_target=src_dir))

    # Prune stale dotai-managed symlinks
    if target_skills_dir.is_dir():
        for entry in sorted(target_skills_dir.iterdir()):
            if entry.name not in desired and _is_dotai_managed_skill_symlink(entry, global_skills_dir):
                ops.append(ProjectionOp("unlink_symlink", entry, f"prune stale dotai skill link {entry.name}"))


def _plan_skill_symlinks_remove(
    target_skills_dir: Path,
    global_skills_dir: Path,
    ops: list[ProjectionOp],
) -> None:
    if not target_skills_dir.is_dir():
        return
    for entry in sorted(target_skills_dir.iterdir()):
        if _is_dotai_managed_skill_symlink(entry, global_skills_dir):
            ops.append(ProjectionOp("unlink_symlink", entry, f"remove dotai skill link {entry.name}"))


def _target_instruction_path(target: TargetName, home: Path) -> Path:
    if target == "codex":
        return home / ".codex" / "AGENTS.md"
    if target == "gemini":
        return home / ".gemini" / "GEMINI.md"
    if target == "agents":
        return home / ".agents" / "AGENTS.md"
    raise ValueError(f"Target {target} does not use a single instruction file")


def _target_skills_dir(target: TargetName, home: Path) -> Path:
    if target == "claude":
        return home / ".claude" / "skills"
    return home / ".agents" / "skills"


def plan_projection(
    target: TargetName,
    config: GlobalConfig,
    home: Path | None = None,
) -> ProjectionPlan:
    """Build a previewable native projection plan for a supported agent target."""
    if target not in SUPPORTED_TARGETS:
        raise ValueError(f"Unsupported target: {target}. Supported: {', '.join(SUPPORTED_TARGETS)}")

    home = (home or Path.home()).expanduser().resolve()
    catalog = load_catalog(config)
    rules = catalog.rules
    skills = catalog.skills
    general_prefs = [p for p in catalog.preferences if p.domain.lower() == "general"]
    notes_body = "\n\n".join(n.body.strip() for n in catalog.notes if n.body.strip())
    global_skills_dir = config.global_skills_path.expanduser().resolve()

    ops: list[ProjectionOp] = []
    warnings: list[str] = []

    if target == "claude":
        rules_dir = home / ".claude" / "rules"
        desired_files: dict[str, str] = {}
        for rule in rules:
            desired_files[f"dotai-{rule.id}.md"] = _render_claude_rule(rule)
        if notes_body:
            notes_name = (
                "dotai-global-notes.md"
                if "dotai-global-notes.md" not in desired_files
                else "dotai--global-notes.md"
            )
            desired_files[notes_name] = _render_claude_notes(notes_body)
        if general_prefs:
            prefs_name = (
                "dotai-preferences.md"
                if "dotai-preferences.md" not in desired_files
                else "dotai--preferences.md"
            )
            desired_files[prefs_name] = _render_claude_preferences(general_prefs)

        for filename, content in sorted(desired_files.items()):
            dest = rules_dir / filename
            if dest.is_symlink():
                warnings.append(f"Skipped symlinked rule file: {dest}")
                continue
            if not dest.exists():
                ops.append(ProjectionOp("create", dest, f"project native Claude rule {filename}", content=content))
            else:
                existing = dest.read_text()
                if MANAGED_RULE_MARKER not in existing:
                    warnings.append(f"Skipped unmanaged file with colliding name: {dest}")
                    continue
                if existing != content:
                    ops.append(ProjectionOp("update", dest, f"update native Claude rule {filename}", content=content))

        # Prune stale dotai-managed rule files
        if rules_dir.is_dir():
            for existing_file in sorted(rules_dir.glob("dotai-*.md")):
                if existing_file.name in desired_files or existing_file.is_symlink():
                    continue
                try:
                    text = existing_file.read_text()
                except OSError:
                    continue
                if MANAGED_RULE_MARKER in text:
                    ops.append(ProjectionOp("remove", existing_file, f"prune stale projected rule {existing_file.name}"))

        _plan_skill_symlinks(skills, _target_skills_dir("claude", home), global_skills_dir, ops, warnings)
        return ProjectionPlan(target="claude", operations=ops, warnings=warnings)

    # codex, gemini, agents -> marker-managed instruction file + ~/.agents/skills/
    has_any_guidance = bool(rules or notes_body or general_prefs)
    inst_path = _target_instruction_path(target, home)
    if has_any_guidance:
        block = _render_compiled_agents_block(target, rules, notes_body, general_prefs)
        _plan_marker_file_upsert(inst_path, target, block, ops, warnings)
    else:
        _plan_marker_file_remove(inst_path, target, ops, warnings)

    _plan_skill_symlinks(skills, _target_skills_dir(target, home), global_skills_dir, ops, warnings)
    return ProjectionPlan(target=target, operations=ops, warnings=warnings)


def plan_projection_remove(
    target: TargetName,
    config: GlobalConfig,
    home: Path | None = None,
    *,
    keep_shared_skills: bool | None = None,
) -> ProjectionPlan:
    """Plan removal of all dotai-projected files and symlinks for a target."""
    if target not in SUPPORTED_TARGETS:
        raise ValueError(f"Unsupported target: {target}. Supported: {', '.join(SUPPORTED_TARGETS)}")

    home = (home or Path.home()).expanduser().resolve()
    global_skills_dir = config.global_skills_path.expanduser().resolve()
    ops: list[ProjectionOp] = []
    warnings: list[str] = []

    if target == "claude":
        rules_dir = home / ".claude" / "rules"
        if rules_dir.is_dir():
            for path in sorted(rules_dir.glob("dotai-*.md")):
                if path.is_symlink():
                    continue
                try:
                    if MANAGED_RULE_MARKER in path.read_text():
                        ops.append(ProjectionOp("remove", path, f"remove projected rule {path.name}"))
                except OSError:
                    continue
        _plan_skill_symlinks_remove(_target_skills_dir("claude", home), global_skills_dir, ops)
        return ProjectionPlan(target="claude", operations=ops, warnings=warnings)

    inst_path = _target_instruction_path(target, home)
    _plan_marker_file_remove(inst_path, target, ops, warnings)
    if keep_shared_skills is None:
        keep_shared_skills = any(
            _has_active_projected_block(other, home)
            for other in _SHARED_SKILLS_TARGETS
            if other != target
        )
    if not keep_shared_skills:
        _plan_skill_symlinks_remove(_target_skills_dir(target, home), global_skills_dir, ops)
    return ProjectionPlan(target=target, operations=ops, warnings=warnings)


def apply_projection_plan(plan: ProjectionPlan, backup_root: Path) -> Path | None:
    """Apply a reviewed projection plan, backing up modified existing files first."""
    if not plan.operations:
        return None

    backup_dir: Path | None = None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")

    def ensure_backup(path: Path) -> None:
        nonlocal backup_dir
        if not path.exists() or path.is_symlink():
            return
        if backup_dir is None:
            backup_dir = backup_root / f"{plan.target}-{stamp}"
            backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup_dir / path.name)

    for op in plan.operations:
        if op.action in ("create", "update"):
            if op.path.is_symlink():
                raise ValueError(f"Refusing to modify symlinked file: {op.path}")
            if op.action == "update":
                ensure_backup(op.path)
            op.path.parent.mkdir(parents=True, exist_ok=True)
            op.path.write_text(op.content or "")
        elif op.action == "remove":
            if op.path.is_symlink():
                raise ValueError(f"Refusing to remove symlinked file: {op.path}")
            ensure_backup(op.path)
            op.path.unlink(missing_ok=True)
        elif op.action == "unlink_symlink":
            if op.path.is_symlink():
                op.path.unlink()
        elif op.action == "symlink":
            if op.symlink_target is None:
                raise ValueError(f"Missing symlink target for {op.path}")
            op.path.parent.mkdir(parents=True, exist_ok=True)
            op.path.symlink_to(op.symlink_target)

    return backup_dir


def projection_status(
    target: TargetName,
    config: GlobalConfig,
    home: Path | None = None,
) -> tuple[str, str]:
    """Return (status_code, detail) for a native projection target."""
    home = (home or Path.home()).expanduser().resolve()
    global_skills_dir = config.global_skills_path.expanduser().resolve()

    if target == "claude":
        rules_dir = home / ".claude" / "rules"
        managed_rules = []
        if rules_dir.is_dir():
            for path in rules_dir.glob("dotai-*.md"):
                if not path.is_symlink():
                    try:
                        if MANAGED_RULE_MARKER in path.read_text():
                            managed_rules.append(path)
                    except OSError:
                        pass
        skills_dir = _target_skills_dir("claude", home)
        managed_skills = [
            p for p in (skills_dir.iterdir() if skills_dir.is_dir() else [])
            if _is_dotai_managed_skill_symlink(p, global_skills_dir)
        ]
        plan = plan_projection("claude", config, home=home)
        if not managed_rules and not managed_skills:
            if not plan.has_changes:
                return "not-configured", "No global rules or skills in ~/.ai/ to project yet"
            return "not-configured", f"{len(plan.operations)} item(s) ready to project into ~/.claude/rules/ & ~/.claude/skills/"
        if plan.has_changes:
            return (
                "out-of-sync",
                f"{len(managed_rules)} projected rule file(s), {len(managed_skills)} linked skill(s); "
                f"{len(plan.operations)} pending update(s)",
            )
        return (
            "configured",
            f"{len(managed_rules)} projected rule file(s) in ~/.claude/rules/, "
            f"{len(managed_skills)} linked skill(s) in ~/.claude/skills/",
        )

    inst_path = _target_instruction_path(target, home)
    skills_dir = _target_skills_dir(target, home)
    start = PROJECTED_START_FMT.format(target=target)
    end = PROJECTED_END_FMT.format(target=target)

    has_block = False
    if inst_path.is_symlink():
        return "unsafe", f"{inst_path} is a symlink"
    if inst_path.exists():
        text = inst_path.read_text()
        if (start in text) != (end in text):
            return "invalid", f"{inst_path} has incomplete dotai projection markers"
        if start in text and text.index(start) > text.index(end):
            return "invalid", f"{inst_path} has reversed dotai projection markers"
        has_block = start in text and end in text

    managed_skills = [
        p for p in (skills_dir.iterdir() if skills_dir.is_dir() else [])
        if _is_dotai_managed_skill_symlink(p, global_skills_dir)
    ]
    plan = plan_projection(target, config, home=home)
    if not has_block and not managed_skills:
        if not plan.has_changes:
            return "not-configured", "No global rules or skills in ~/.ai/ to project yet"
        return "not-configured", f"{len(plan.operations)} item(s) ready to project into {inst_path}"
    if plan.has_changes:
        return "out-of-sync", f"Projected to {inst_path} ({len(managed_skills)} linked skill(s)); {len(plan.operations)} pending update(s)"
    return "configured", f"Projected to {inst_path} ({len(managed_skills)} linked skill(s))"
