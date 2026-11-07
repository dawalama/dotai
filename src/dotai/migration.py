"""Lossless migration of legacy dotai skills and roles to native packages."""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from .models import GlobalConfig
from .roles import parse_role_file
from .utils import generate_id


@dataclass(frozen=True)
class MigrationAction:
    """One planned or applied migration change."""

    kind: Literal["skill", "role"]
    source_path: Path
    target_path: Path
    action: str
    description: str
    warnings: list[str] = field(default_factory=list)
    backup_path: Path | None = None

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "source_path": str(self.source_path),
            "target_path": str(self.target_path),
            "action": self.action,
            "description": self.description,
            "warnings": self.warnings,
            "backup_path": str(self.backup_path) if self.backup_path else None,
        }


@dataclass
class MigrationPlan:
    """A collection of migration actions for a given scope."""

    scope: str
    actions: list[MigrationAction] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return bool(self.actions)

    def to_dict(self) -> dict:
        return {
            "scope": self.scope,
            "has_changes": self.has_changes,
            "actions": [a.to_dict() for a in self.actions],
        }


def _extract_frontmatter_dict(content: str) -> dict[str, str]:
    frontmatter: dict[str, str] = {}
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].strip().split("\n"):
                if ":" in line:
                    key, value = line.split(":", 1)
                    frontmatter[key.strip().lower()] = value.strip()
    return frontmatter


def plan_migration(
    config: GlobalConfig,
    *,
    project_name: str | None = None,
    scope_path: Path | None = None,
    include_skills: bool = True,
    include_roles: bool = True,
) -> MigrationPlan:
    """Plan lossless migration of legacy folder skills and roles to native packages.

    Does not modify any files on disk.
    """
    if scope_path:
        ai_dirs = [scope_path / ".ai" if (scope_path / ".ai").exists() else scope_path]
        scope_label = scope_path.name
    elif project_name:
        proj = config.get_project(project_name)
        if not proj:
            raise ValueError(f"Project '{project_name}' not found")
        ai_dirs = [proj.full_ai_path]
        scope_label = project_name
    else:
        ai_dirs = [config.global_ai_dir]
        for proj in config.projects:
            if proj.full_ai_path.exists():
                ai_dirs.append(proj.full_ai_path)
        scope_label = "all"

    actions: list[MigrationAction] = []

    for ai_dir in ai_dirs:
        if not ai_dir.exists():
            continue

        skills_dir = ai_dir / "skills"
        roles_dir = ai_dir / "roles"

        # 1. Plan legacy skill migrations (folder skills with main.md -> SKILL.md)
        if include_skills and skills_dir.is_dir():
            for item in sorted(skills_dir.iterdir()):
                if not item.is_dir():
                    continue

                main_file = item / "main.md"
                skill_file = item / "SKILL.md"

                if main_file.exists() and not skill_file.exists():
                    warnings = [
                        "Adopted canonical native SKILL.md package format.",
                        "Tool restrictions and hooks may vary across agent harnesses.",
                    ]
                    content = main_file.read_text()
                    fm = _extract_frontmatter_dict(content)
                    if "allowed-tools" in fm:
                        warnings.append(
                            "allowed-tools metadata does not provide an enforced security boundary in native harnesses."
                        )

                    actions.append(
                        MigrationAction(
                            kind="skill",
                            source_path=main_file,
                            target_path=skill_file,
                            action="migrate-folder-skill",
                            description=f"Migrate legacy folder skill '{item.name}/main.md' to canonical 'SKILL.md'",
                            warnings=warnings,
                        )
                    )

        # 2. Plan legacy role migrations (roles/*.md -> skills/<role-id>/SKILL.md)
        if include_roles and roles_dir.is_dir():
            for role_file in sorted(roles_dir.glob("*.md")):
                role_id = role_file.stem
                target_skill_dir = skills_dir / role_id
                target_skill_file = target_skill_dir / "SKILL.md"

                warnings = [
                    "Roles as an automatic persona abstraction are retired.",
                    "Migrated to user-authored perspective skill.",
                    "Preserved complete persona, principles, and anti-patterns losslessly.",
                ]

                actions.append(
                    MigrationAction(
                        kind="role",
                        source_path=role_file,
                        target_path=target_skill_file,
                        action="migrate-role-to-skill",
                        description=f"Migrate legacy role '{role_file.name}' to native perspective skill '{role_id}/SKILL.md'",
                        warnings=warnings,
                    )
                )

    return MigrationPlan(scope=scope_label, actions=actions)


def apply_migration(
    plan: MigrationPlan,
    backup_root: Path,
    dry_run: bool = False,
) -> list[MigrationAction]:
    """Execute planned migration actions with safety backups.

    If dry_run is True, returns actions without touching disk.
    """
    if dry_run or not plan.actions:
        return plan.actions

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    session_backup = backup_root / f"migration-{timestamp}"
    applied: list[MigrationAction] = []

    for action in plan.actions:
        # Create backup
        backup_path: Path | None = None
        if action.source_path.exists():
            rel_backup = session_backup / action.source_path.name
            session_backup.mkdir(parents=True, exist_ok=True)
            shutil.copy2(action.source_path, rel_backup)
            backup_path = rel_backup

        if action.action == "migrate-folder-skill":
            # Losslessly move main.md to SKILL.md
            action.target_path.parent.mkdir(parents=True, exist_ok=True)
            content = action.source_path.read_text()
            action.target_path.write_text(content)
            action.source_path.unlink()

            # Store dotai-specific metadata if not present
            metadata_file = action.target_path.parent / ".dotai-metadata.json"
            if not metadata_file.exists():
                fm = _extract_frontmatter_dict(content)
                meta = {
                    "migrated_at": datetime.now(timezone.utc).isoformat(),
                    "source": "legacy-main-md",
                }
                if "category" in fm:
                    meta["category"] = fm["category"]
                if "trigger" in fm:
                    meta["trigger"] = fm["trigger"]
                if "allowed-tools" in fm:
                    meta["allowed-tools"] = fm["allowed-tools"]
                metadata_file.write_text(json.dumps(meta, indent=2) + "\n")

        elif action.action == "migrate-role-to-skill":
            # Convert legacy role into user-authored perspective skill
            role = parse_role_file(action.source_path)
            if role:
                action.target_path.parent.mkdir(parents=True, exist_ok=True)
                lines = [
                    "---",
                    f"name: {role.name}",
                    f"description: {role.description}",
                    f"tags: [{', '.join(role.tags + ['role', 'perspective', 'migrated'])}]",
                    "---",
                    "",
                    role.to_prompt(),
                    "",
                ]
                action.target_path.write_text("\n".join(lines))
                # Remove old role file now that it is safely migrated and backed up
                action.source_path.unlink()

        applied.append(
            MigrationAction(
                kind=action.kind,
                source_path=action.source_path,
                target_path=action.target_path,
                action=action.action,
                description=action.description,
                warnings=action.warnings,
                backup_path=backup_path,
            )
        )

    return applied
