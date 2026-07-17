"""Deterministic, on-demand context resolution for coding agents."""

from __future__ import annotations

import fnmatch
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .models import (
    GlobalConfig,
    PreferencePack,
    Role,
    Rule,
    Skill,
    SkillCategory,
)
from .preferences import resolve_preference_packs
from .roles import load_all_roles, load_roles_from_dir
from .rules import load_rules_from_dir, resolve_rules_for_project
from .skills import load_all_skills, load_skills_from_dir


@dataclass(frozen=True)
class Selection:
    """A selected knowledge item and the deterministic reason it was loaded."""

    kind: str
    item_id: str
    reason: str


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

    @property
    def requires_files(self) -> bool:
        """Whether this workflow can miss scoped rules without affected files."""
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
            "## Universal Rule Index",
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
        if self.rule_summaries:
            for rule in self.rule_summaries:
                lines.append(f"- **{rule.name}** (`{rule.id}`): {rule.description}")
        else:
            lines.append("- No universal rules are active.")

        if self.rules:
            lines.extend(["", "## Expanded Rules", ""])
            for rule in self.rules:
                lines.append(f"Selected because: {self.reason_for('rule', rule.id)}")
                lines.append("")
                lines.append(rule.to_prompt())
                lines.append("")

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
        "universal_rules": [rule.id for rule in resolved.rule_summaries],
        "expanded_rules": [rule.id for rule in resolved.rules],
        "preferences": [pack.id for pack in resolved.preferences],
        "skill": resolved.skill.id if resolved.skill else None,
        "role": resolved.role.id if resolved.role else None,
        "selections": [selection.__dict__ for selection in resolved.selections],
    }
    temporary = receipts_dir / f".{agent_id}.json.tmp"
    temporary.write_text(json.dumps(payload, indent=2) + "\n")
    temporary.replace(path)

    history_dir = receipts_dir / "history" / agent_id
    history_dir.mkdir(parents=True, exist_ok=True)
    history_path = history_dir / f"{uuid.uuid4().hex}.json"
    history_temporary = history_dir / f".{history_path.name}.tmp"
    history_temporary.write_text(json.dumps(payload, indent=2) + "\n")
    history_temporary.replace(history_path)
    history_files = sorted(
        (
            item for item in history_dir.glob("*.json")
            if item.is_file() and not item.is_symlink()
        ),
        key=lambda item: item.stat().st_mtime_ns,
        reverse=True,
    )
    for stale in history_files[500:]:
        stale.unlink()
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


def _matches_file(rule: Rule, files: list[str]) -> str | None:
    for filename in files:
        normalized = filename.replace("\\", "/").lstrip("./")
        for pattern in rule.globs:
            if pattern in {"*", "**", "**/*"}:
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


def _route_skill(skills: list[Skill], task: str) -> Skill | None:
    """Select a skill only when one explicit alias appears unambiguously."""
    normalized_task = task.lower().replace("_", "-").replace("/", "")
    words = set(re.findall(r"[a-z0-9-]+", normalized_task))
    matches: list[Skill] = []
    for skill in skills:
        aliases: set[str] = set()
        if skill.trigger:
            trigger = skill.trigger.lower().lstrip("/")
            aliases.add(trigger)
            if trigger.startswith("run_"):
                aliases.add(trigger[4:])
        aliases.add(skill.id.lower())
        for alias in aliases:
            alias_words = set(re.findall(r"[a-z0-9-]+", alias.replace("_", "-")))
            if alias_words and alias_words <= words:
                matches.append(skill)
                break
    return matches[0] if len(matches) == 1 else None


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

    rules = resolve_rules_for_project(config, project_name)
    local_rules = load_rules_from_dir(project_path / ".ai" / "rules", project_name or "local")
    by_id = {r.id: r for r in rules}
    by_id.update({r.id: r for r in local_rules if r.enabled})
    rules = list(by_id.values())

    result = ResolvedContext(
        project_path=project_path, task=task, files=files, contexts=contexts
    )
    for rule in rules:
        universal = not rule.globs or any(g in {"*", "**", "**/*"} for g in rule.globs)
        if universal:
            result.rule_summaries.append(rule)

        reason = _matches_file(rule, files)
        if not reason and contexts and set(t.lower() for t in rule.tags) & set(contexts):
            matched = sorted(set(t.lower() for t in rule.tags) & set(contexts))
            reason = f"rule tag matches context: {', '.join(matched)}"
        if not reason and rule.id.lower() in requested_rules:
            reason = "explicitly requested"
        if reason:
            result.rules.append(rule)
            result.selections.append(Selection("rule", rule.id, reason))

    unknown_rules = requested_rules - {r.id.lower() for r in rules}
    if unknown_rules:
        raise ValueError(f"Unknown rule(s): {', '.join(sorted(unknown_rules))}")

    active_prefs = resolve_preference_packs(
        config, project_name, project_path, extra=extra_prefs
    )
    for pack in active_prefs:
        if pack.domain.lower() in domains:
            result.preferences.append(pack)
            result.selections.append(Selection(
                "preference", pack.id, f"active pack matches requested domain `{pack.domain}`"
            ))

    scoped_skills = [
        s for s in load_all_skills(config)
        if s.scope in {"global", project_name}
    ]
    local_skills = load_skills_from_dir(
        project_path / ".ai" / "skills", project_name or "local"
    )
    scoped_skills = list({s.id: s for s in [*scoped_skills, *local_skills]}.values())
    scoped_roles = [
        r for r in load_all_roles(config)
        if r.scope in {"global", project_name}
    ]
    local_roles = load_roles_from_dir(
        project_path / ".ai" / "roles", project_name or "local"
    )
    scoped_roles = list({r.id: r for r in [*scoped_roles, *local_roles]}.values())
    result.skill = _find(scoped_skills, skill_id, "skill")
    routed_skill = False
    if not result.skill and task:
        result.skill = _route_skill(scoped_skills, task)
        routed_skill = result.skill is not None
    requested_role = role_id or (result.skill.role if result.skill else None)
    result.role = _find(scoped_roles, requested_role, "role")
    if result.skill:
        reason = (
            f"unambiguous task alias in `{task}`"
            if routed_skill else "explicitly requested"
        )
        result.selections.append(Selection("skill", result.skill.id, reason))
    if result.role:
        reason = "selected by skill" if result.skill and not role_id else "explicitly requested"
        result.selections.append(Selection("role", result.role.id, reason))
    return result
