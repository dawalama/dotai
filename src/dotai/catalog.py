"""One scoped view of knowledge for context resolution and exports."""

from dataclasses import dataclass
from pathlib import Path

from .models import GlobalConfig, PreferencePack, Role, Rule, Skill
from .preferences import load_active_pack_ids, load_preferences_from_dir
from .roles import load_roles_from_dir
from .rules import load_rules_from_dir, load_rules_md
from .scope import KnowledgeScope, resolve_scope
from .skills import load_skills_from_dir


@dataclass(frozen=True)
class FreeformNote:
    scope: str
    path: Path
    body: str


@dataclass
class KnowledgeCatalog:
    scope: KnowledgeScope
    rules: list[Rule]
    skills: list[Skill]
    roles: list[Role]
    preferences: list[PreferencePack]
    notes: list[FreeformNote]
    rule_roots: dict[str, Path | None]


def load_catalog(
    config: GlobalConfig,
    project_name: str | None = None,
    project_path: Path | None = None,
    extra_prefs: list[str] | None = None,
) -> KnowledgeCatalog:
    scope = resolve_scope(config, project_name, project_path)
    rules: dict[str, Rule] = {}
    skills: dict[str, Skill] = {}
    roles: dict[str, Role] = {}
    preferences: dict[str, PreferencePack] = {}
    notes: list[FreeformNote] = []
    rule_roots: dict[str, Path | None] = {}
    for entry in scope.directories:
        label, directory = entry.scope, entry.path
        for rule in load_rules_from_dir(directory / "rules", label):
            if directory != scope.directories[0].path or rule.id not in scope.disabled_rules:
                rules[rule.id] = rule
                rule_roots[rule.id] = entry.root_path
        skills.update((s.id, s) for s in load_skills_from_dir(directory / "skills", label))
        roles.update((r.id, r) for r in load_roles_from_dir(directory / "roles", label))
        preferences.update((p.id, p) for p in load_preferences_from_dir(directory / "preferences", label))
        body = load_rules_md(directory)
        if body:
            notes.append(FreeformNote(label, directory / "rules.md", body))

    active = list(extra_prefs or [])
    for entry in reversed(scope.directories):
        active.extend(load_active_pack_ids(entry.path))
    active = list(dict.fromkeys(active))
    return KnowledgeCatalog(
        scope, [r for r in rules.values() if r.enabled], list(skills.values()),
        list(roles.values()),
        [preferences[i] for i in active if i in preferences and preferences[i].enabled],
        notes, rule_roots,
    )
