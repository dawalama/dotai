"""Discover applicable knowledge directories without scanning other projects."""

import subprocess
from dataclasses import dataclass
from pathlib import Path

from .models import GlobalConfig


def find_git_root(project_path: Path) -> Path | None:
    """Find the current worktree root without changing Git state."""
    try:
        result = subprocess.run(
            ["git", "-C", str(project_path), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=False,
        )
    except FileNotFoundError:
        return None
    return Path(result.stdout.strip()).resolve() if result.returncode == 0 else None


@dataclass(frozen=True)
class KnowledgeDirectory:
    scope: str
    path: Path
    root_path: Path | None


@dataclass(frozen=True)
class KnowledgeScope:
    project_path: Path | None
    project_name: str | None
    directories: list[KnowledgeDirectory]
    disabled_rules: frozenset[str]


def resolve_scope(
    config: GlobalConfig,
    project_name: str | None = None,
    project_path: Path | None = None,
) -> KnowledgeScope:
    """Order global and applicable ancestor directories from weakest to strongest.

    A Git worktree bounds discovery. Outside Git, a registered project bounds it;
    an unregistered path uses only its own .ai directory.
    """
    project = config.get_project(project_name) if project_name else None
    if project_name and project is None:
        raise ValueError(f"Project '{project_name}' not found")
    path = project_path.expanduser().resolve() if project_path is not None else None
    if path is None and project:
        path = project.path.expanduser().resolve()
    global_dir = config.global_ai_dir.expanduser().resolve()
    if path is None:
        return KnowledgeScope(None, None, [KnowledgeDirectory("global", global_dir, None)], frozenset())

    git_root = find_git_root(path)
    registered = {
        candidate.path.expanduser().resolve(): candidate
        for candidate in config.projects
        if path.is_relative_to(candidate.path.expanduser().resolve())
        and (git_root is None or candidate.path.expanduser().resolve().is_relative_to(git_root))
    }
    if project:
        registered_path = project.path.expanduser().resolve()
        if not path.is_relative_to(registered_path) or (
            git_root and not registered_path.is_relative_to(git_root)
        ):
            raise ValueError(f"Path '{path}' is outside project '{project.name}'")
    else:
        project = max(registered.values(), key=lambda p: len(p.path.expanduser().resolve().parts), default=None)

    boundary = git_root or (project.path.expanduser().resolve() if project else path)
    directories = [KnowledgeDirectory("global", global_dir, boundary)]
    ancestors = [path, *path.parents]
    ancestors = list(reversed(ancestors[:ancestors.index(boundary) + 1]))
    seen = {global_dir}
    disabled_rules: set[str] = set()
    for ancestor in ancestors:
        owner = registered.get(ancestor)
        if owner:
            disabled_rules.update(owner.disabled_rules)
        ai_dir = (owner.full_ai_path if owner else ancestor / ".ai").expanduser().resolve()
        if ai_dir not in seen:
            scope = owner.name if owner else f"local:{ancestor}"
            directories.append(KnowledgeDirectory(scope, ai_dir, ancestor))
            seen.add(ai_dir)
    return KnowledgeScope(
        path, project.name if project else None, directories,
        frozenset(disabled_rules),
    )
