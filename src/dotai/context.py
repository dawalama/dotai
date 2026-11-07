"""Deterministic, on-demand context resolution for coding agents."""

from __future__ import annotations

import fnmatch
import json
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .models import (
    CATCH_ALL_GLOBS,
    GlobalConfig,
    PreferencePack,
    Role,
    Rule,
    Skill,
    SkillCategory,
)
from .catalog import FreeformNote, load_catalog


@dataclass(frozen=True)
class Selection:
    """A selected knowledge item and the deterministic reason it was loaded."""

    kind: str
    item_id: str
    reason: str
    source: str | None = None


@dataclass
class ResolvedContext:
    """Knowledge selected for one task without mutating any source files."""

    project_path: Path
    task: str = ""
    files: list[str] = field(default_factory=list)
    contexts: list[str] = field(default_factory=list)
    rule_summaries: list[Rule] = field(default_factory=list)
    rules: list[Rule] = field(default_factory=list)
    preferences: list[PreferencePack] = field(default_factory=list)
    skill: Skill | None = None
    role: Role | None = None
    selections: list[Selection] = field(default_factory=list)
    notes: list[FreeformNote] = field(default_factory=list)
    available_preferences: list[PreferencePack] = field(default_factory=list)
    scoped_rule_count: int = 0

    @property
    def requires_files(self) -> bool:
        """Whether this workflow can miss scoped rules without affected files."""
        if self.scoped_rule_count:
            return True
        if not self.skill or not self.skill.category:
            return False
        return self.skill.category in {
            SkillCategory.CODE_QUALITY,
            SkillCategory.DEBUGGING,
            SkillCategory.VERIFICATION,
            SkillCategory.SCAFFOLDING,
            SkillCategory.MAINTENANCE,
            SkillCategory.DEPLOYMENT,
        }

    @property
    def provisional(self) -> bool:
        return self.requires_files and not self.files

    def reason_for(self, kind: str, item_id: str) -> str:
        match = next(
            (s for s in self.selections if s.kind == kind and s.item_id == item_id),
            None,
        )
        return match.reason if match else "selected"

    def to_dict(self) -> dict:
        return {
            "project_path": str(self.project_path),
            "task": self.task,
            "files": self.files,
            "contexts": self.contexts,
            "requires_files": self.requires_files,
            "provisional": self.provisional,
            "file_scope": "provided" if self.files else "unknown",
            "rule_summaries": [
                {"id": r.id, "description": r.description, "globs": r.globs}
                for r in self.rule_summaries
            ],
            "rules": [
                {
                    "id": r.id,
                    "description": r.description,
                    "globs": r.globs,
                    "body": r.body,
                    "reason": self.reason_for("rule", r.id),
                }
                for r in self.rules
            ],
            "preferences": [
                {
                    "id": p.id,
                    "domain": p.domain,
                    "body": p.body,
                    "reason": self.reason_for("preference", p.id),
                }
                for p in self.preferences
            ],
            "available_preferences": [
                {"id": p.id, "domain": p.domain, "description": p.description}
                for p in self.available_preferences
            ],
            "notes": [
                {"source": str(n.path), "scope": n.scope, "body": n.body}
                for n in self.notes
            ],
            "skill": (
                {"id": self.skill.id, "prompt": self.skill.to_prompt(self.role)}
                if self.skill else None
            ),
            "role": (
                {"id": self.role.id, "prompt": self.role.to_prompt()}
                if self.role and not self.skill else None
            ),
            "selections": [s.__dict__ for s in self.selections],
        }

    def to_prompt(self) -> str:
        lines = [
            "# Resolved dotai Context",
            "",
            "This is developer-controlled engineering judgment selected for the current task.",
            "Repository and organization instructions are authoritative. Personal dotai",
            "context is supplemental and must be ignored where it conflicts with team guidance.",
            "",
        ]
        if self.provisional:
            lines.extend([
                "## Provisional Resolution — Files Required",
                "",
                "This workflow can be affected by file-scoped rules, but no affected files",
                "were supplied. Discover the relevant files, then run `dotai context` again",
                "with `--files` before substantive review, editing, or implementation.",
                "Do not treat this initial resolution as complete.",
                "",
            ])
        if self.rules:
            lines.extend(["", "## Expanded Rules", ""])
            for rule in self.rules:
                lines.append(f"Selected because: {self.reason_for('rule', rule.id)}")
                lines.append("")
                lines.append(rule.to_prompt())
                lines.append("")

        if self.notes:
            lines.extend(["", "## Freeform Conventions (rules.md)", ""])
            for note in self.notes:
                lines.extend([f"### {note.scope}", f"Source: `{note.path}`", "", note.body, ""])

        if self.available_preferences:
            lines.extend(["", "## Available Active Preference Domains", ""])
            for pack in self.available_preferences:
                lines.append(f"- `{pack.id}`: {pack.description} (domain: `{pack.domain}`)")
            lines.extend(["", "Load a relevant domain with `--domain <domain>` or a named pack with `--with-prefs <id>`.", ""])

        if self.preferences:
            lines.extend(["", "## Expanded Preferences", ""])
            for pack in self.preferences:
                lines.append(f"Selected because: {self.reason_for('preference', pack.id)}")
                lines.append("")
                lines.append(pack.to_prompt())
                lines.append("")

        if self.skill:
            lines.extend([
                "", "## Selected Skill", "",
                f"Selected because: {self.reason_for('skill', self.skill.id)}", "",
                self.skill.to_prompt(self.role), "",
            ])
        elif self.role:
            lines.extend([
                "", "## Selected Role", "",
                f"Selected because: {self.reason_for('role', self.role.id)}", "",
                self.role.to_prompt(), "",
            ])
        return "\n".join(lines).rstrip() + "\n"


def save_resolution_receipt(
    resolved: ResolvedContext, agent: str, receipts_dir: Path
) -> Path:
    """Persist selection metadata only, never expanded bodies or source content."""
    agent_id = agent.strip().lower()
    if not re.fullmatch(r"[a-z0-9-]+", agent_id):
        raise ValueError(f"Invalid agent receipt id: {agent}")
    receipts_dir.mkdir(parents=True, exist_ok=True)
    path = receipts_dir / f"{agent_id}.json"
    payload = {
        "agent": agent_id,
        "resolved_at": datetime.now(timezone.utc).isoformat(),
        "project_path": str(resolved.project_path),
        "task": resolved.task,
        "files": resolved.files,
        "contexts": resolved.contexts,
        "requires_files": resolved.requires_files,
        "provisional": resolved.provisional,
        "file_scope": "provided" if resolved.files else "unknown",
        "universal_rules": [rule.id for rule in resolved.rule_summaries],
        "expanded_rules": [rule.id for rule in resolved.rules],
        "preferences": [pack.id for pack in resolved.preferences],
        "notes": [str(note.path) for note in resolved.notes],
        "skill": resolved.skill.id if resolved.skill else None,
        "role": resolved.role.id if resolved.role else None,
        "selections": [selection.__dict__ for selection in resolved.selections],
    }
    temporary = receipts_dir / f".{agent_id}.{uuid.uuid4().hex}.json.tmp"
    temporary.write_text(json.dumps(payload, indent=2) + "\n")
    temporary.replace(path)

    history_dir = receipts_dir / "history" / agent_id
    history_dir.mkdir(parents=True, exist_ok=True)
    history_path = history_dir / f"{uuid.uuid4().hex}.json"
    history_temporary = history_dir / f".{history_path.name}.tmp"
    history_temporary.write_text(json.dumps(payload, indent=2) + "\n")
    history_temporary.replace(history_path)
    history_files = []
    for item in history_dir.glob("*.json"):
        if item.is_symlink() or not item.is_file():
            continue
        try:
            history_files.append((item.stat().st_mtime_ns, item))
        except FileNotFoundError:
            continue  # Another writer may already have pruned this event.
    history_files.sort(reverse=True)
    for _, stale in history_files[500:]:
        stale.unlink(missing_ok=True)
    return path


def load_resolution_receipt(agent: str, receipts_dir: Path) -> dict | None:
    """Load a local adapter receipt, returning None when absent or invalid."""
    agent_id = agent.strip().lower()
    if not re.fullmatch(r"[a-z0-9-]+", agent_id):
        raise ValueError(f"Invalid agent receipt id: {agent}")
    path = receipts_dir / f"{agent_id}.json"
    if not path.is_file() or path.is_symlink():
        return None
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _matches_file(
    rule: Rule, files: list[str], project_path: Path, rule_root: Path | None,
) -> str | None:
    for filename in files:
        normalized = filename.replace("\\", "/")
        if rule_root:
            try:
                logical_path = Path(os.path.abspath(project_path / normalized))
                normalized = logical_path.relative_to(rule_root).as_posix()
            except ValueError:
                continue  # This path lies outside the rule's owning scope.
        for pattern in rule.globs:
            if pattern in CATCH_ALL_GLOBS:
                continue
            if fnmatch.fnmatch(normalized, pattern) or fnmatch.fnmatch(Path(normalized).name, pattern):
                return f"file `{filename}` matches `{pattern}`"
    return None


def _find(items: list, requested: str | None, kind: str):
    if not requested:
        return None
    key = requested.strip().lower().lstrip("/")
    for item in items:
        candidates = {item.id.lower(), item.name.lower()}
        file_path = getattr(item, "file_path", None)
        if file_path:
            candidates.add(file_path.stem.lower())
        trigger = getattr(item, "trigger", None)
        if trigger:
            candidates.add(trigger.lower().lstrip("/"))
        if key in candidates:
            return item
    raise ValueError(f"Unknown {kind}: {requested}")


def resolve_context(
    config: GlobalConfig,
    project_path: Path,
    project_name: str | None = None,
    *,
    task: str = "",
    files: list[str] | None = None,
    contexts: list[str] | None = None,
    domains: list[str] | None = None,
    skill_id: str | None = None,
    role_id: str | None = None,
    rule_ids: list[str] | None = None,
    extra_prefs: list[str] | None = None,
) -> ResolvedContext:
    """Resolve relevant context using explicit metadata, never semantic guessing."""
    files = files or []
    contexts = [c.lower() for c in (contexts or [])]
    domains = [d.lower() for d in (domains or [])]
    requested_rules = {r.lower() for r in (rule_ids or [])}

    catalog = load_catalog(config, project_name, project_path, extra_prefs)
    rules = catalog.rules

    result = ResolvedContext(
        project_path=catalog.scope.project_path, task=task, files=files, contexts=contexts,
        notes=catalog.notes, scoped_rule_count=sum(not r.is_universal for r in rules),
    )
    for note in result.notes:
        result.selections.append(Selection(
            "note", str(note.path), f"freeform conventions in scope `{note.scope}`", str(note.path)
        ))
    for rule in rules:
        if rule.is_universal:
            result.rule_summaries.append(rule)

        reason = _matches_file(rule, files, result.project_path, catalog.rule_roots[rule.id])
        if not reason and contexts and set(t.lower() for t in rule.tags) & set(contexts):
            matched = sorted(set(t.lower() for t in rule.tags) & set(contexts))
            reason = f"rule tag matches context: {', '.join(matched)}"
        if not reason and rule.id.lower() in requested_rules:
            reason = "explicitly requested"
        if not reason and rule.is_universal:
            reason = "universal rule applies to every task"
        if reason:
            result.rules.append(rule)
            result.selections.append(Selection("rule", rule.id, reason, str(rule.file_path)))

    unknown_rules = requested_rules - {r.id.lower() for r in rules}
    if unknown_rules:
        raise ValueError(f"Unknown rule(s): {', '.join(sorted(unknown_rules))}")

    for pack in catalog.preferences:
        reason = None
        if pack.id in (extra_prefs or []):
            reason = "explicitly requested preference pack"
        elif pack.domain.lower() == "general":
            reason = "active general preference pack"
        elif pack.domain.lower() in domains:
            reason = f"active pack matches requested domain `{pack.domain}`"
        if reason:
            result.preferences.append(pack)
            result.selections.append(Selection(
                "preference", pack.id, reason, str(pack.file_path)
            ))
        else:
            result.available_preferences.append(pack)

    result.skill = _find(catalog.skills, skill_id, "skill")
    if result.skill:
        result.selections.append(Selection("skill", result.skill.id, "explicitly requested"))

    # Role resolution is transitional/legacy: resolved only when explicitly requested
    if role_id:
        result.role = _find(catalog.roles, role_id, "role")
        if result.role:
            result.selections.append(Selection("role", result.role.id, "explicitly requested"))
    return result
