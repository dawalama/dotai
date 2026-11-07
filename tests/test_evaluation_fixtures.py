"""Behavioral evaluation fixtures comparing context delivery strategies.

Compares three conditions across representative private-guidance tasks:
1. Native agent alone (unassisted default)
2. Static instruction file + all skills/rules dump
3. dotai deterministic scoped resolution
"""

from pathlib import Path
import json
from dotai.context import resolve_context
from dotai.models import GlobalConfig, PreferencePack, ProjectConfig, Rule, Skill, SkillCategory


def test_behavioral_comparison_fixture(tmp_path):
    global_ai = tmp_path / "global_ai"
    repo_a = tmp_path / "repo_a"
    (repo_a / ".ai" / "rules").mkdir(parents=True)
    (global_ai / "rules").mkdir(parents=True)
    (global_ai / "preferences").mkdir(parents=True)
    (global_ai / "skills").mkdir(parents=True)

    # 1. Cross-repository preference
    pref_content = "---\nname: CLI Style\ndomain: cli\n---\nUse subcommands, lowercase flags.\n"
    (global_ai / "preferences" / "cli.md").write_text(pref_content)
    (global_ai / "preferences-active.json").write_text(json.dumps({"packs": ["cli"]}))

    # 2. File-scoped constraint
    react_rule = "---\nname: react-hooks\nglobs: '*.tsx'\n---\nDerive state during render; useEffect only for sync.\n"
    (global_ai / "rules" / "react-hooks.md").write_text(react_rule)

    # 3. Irrelevant guidance (Python constraint that must not load for TSX)
    python_rule = "---\nname: python-types\nglobs: '*.py'\n---\nUse typing.Optional and pydantic v2.\n"
    (global_ai / "rules" / "python-types.md").write_text(python_rule)

    # 4. Local override in repo_a
    local_override = "---\nname: react-hooks\nglobs: '*.tsx'\n---\nRepo A specific override for React.\n"
    (repo_a / ".ai" / "rules" / "react-hooks.md").write_text(local_override)

    config = GlobalConfig(
        global_ai_dir=global_ai,
        projects=[ProjectConfig(name="repo_a", path=repo_a)],
    )

    # Task: Editing a React file in Repo A
    task_desc = "Update the user profile header component"
    affected_files = ["src/components/Header.tsx"]

    # --- Condition A: Native agent alone ---
    # Has 0 private guidance delivered unless user re-prompts manually.
    delivered_guidance_a = []
    assert len(delivered_guidance_a) == 0

    # --- Condition B: Static instruction file dump ---
    # Unconditionally includes all rules (both Python and React) and full text
    dump_text = (
        pref_content
        + react_rule
        + python_rule
        + local_override
    )
    # Both relevant and irrelevant guidance are loaded; local override conflicts with global
    assert "python-types" in dump_text
    assert "Repo A specific override" in dump_text
    dump_size = len(dump_text)

    # --- Condition C: dotai scoped resolution ---
    resolved = resolve_context(
        config,
        project_path=repo_a,
        project_name="repo_a",
        task=task_desc,
        files=affected_files,
        domains=["cli"],
    )

    resolved_rule_ids = [r.id for r in resolved.rules]
    # Scoped matching:
    # 1. react-hooks is loaded because Header.tsx matches *.tsx
    assert "react-hooks" in resolved_rule_ids
    # 2. Local override took precedence over global rule
    matching_rule = next(r for r in resolved.rules if r.id == "react-hooks")
    assert "Repo A specific override" in matching_rule.body
    # 3. Irrelevant guidance (python-types) is excluded!
    assert "python-types" not in resolved_rule_ids
    # 4. Requested CLI preference pack is loaded
    assert any(p.domain == "cli" for p in resolved.preferences)

    # 5. Measure context efficiency
    dotai_prompt = resolved.to_prompt()
    assert "python-types" not in dotai_prompt
    assert "Repo A specific override" in dotai_prompt
    assert "Selected because: file `src/components/Header.tsx` matches `*.tsx`" in dotai_prompt


def test_provisional_resolution_behavior_when_files_unknown(tmp_path):
    ai_dir = tmp_path / "global_ai"
    (ai_dir / "rules").mkdir(parents=True)

    # Add a file-scoped rule
    (ai_dir / "rules" / "api-rule.md").write_text(
        "---\nname: api-rule\nglobs: 'src/api/*.py'\n---\nValidate tokens on all API endpoints.\n"
    )

    config = GlobalConfig(global_ai_dir=ai_dir)

    # Step 1: Initial call without files
    initial = resolve_context(config, tmp_path, task="Add a new billing endpoint")
    assert initial.scoped_rule_count == 1
    assert initial.requires_files is True
    assert initial.provisional is True
    assert "Provisional Resolution — Files Required" in initial.to_prompt()
    assert len(initial.rules) == 0  # File-scoped rule stayed unloaded

    # Step 2: Second call with discovered affected files
    complete = resolve_context(
        config,
        tmp_path,
        task="Add a new billing endpoint",
        files=["src/api/billing.py"],
    )
    assert complete.provisional is False
    assert len(complete.rules) == 1
    assert complete.rules[0].id == "api-rule"
    assert "Provisional Resolution" not in complete.to_prompt()
