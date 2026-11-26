"""Tests for native multi-agent projection (claude, codex, gemini, agents)."""

from pathlib import Path

from typer.testing import CliRunner

from dotai import store
from dotai.cli import app
from dotai.models import GlobalConfig
from dotai.projection import (
    MANAGED_RULE_MARKER,
    PROJECTED_START_FMT,
    apply_projection_plan,
    plan_projection,
    plan_projection_remove,
    projection_status,
)
from dotai.rules import format_rule_markdown


def _write_rule(rules_dir: Path, rule_id: str, name: str, description: str, body: str, globs=None):
    (rules_dir / f"{rule_id}.md").write_text(
        format_rule_markdown(name=name, description=description, body=body, globs=globs)
    )


def _make_config(tmp_path: Path) -> GlobalConfig:
    ai_dir = tmp_path / ".ai"
    (ai_dir / "rules").mkdir(parents=True)
    (ai_dir / "skills").mkdir(parents=True)
    (ai_dir / "preferences").mkdir(parents=True)
    return GlobalConfig(global_ai_dir=ai_dir)


def test_claude_projection_emits_native_paths_frontmatter_and_prunes_stale(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    config = _make_config(tmp_path)

    _write_rule(
        config.global_rules_path,
        "react-derived-state",
        "React Derived State",
        "Derive state during render",
        "Always derive state during render instead of syncing via useEffect.",
        globs=["*.tsx", "src/**/*.ts"],
    )
    _write_rule(
        config.global_rules_path,
        "no-secrets",
        "No Secrets",
        "Never log secrets",
        "Never print credentials or API tokens to stdout.",
    )

    # Add a native folder skill
    skill_dir = config.global_skills_path / "release"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: release\ndescription: Release flow\n---\n\nRun release steps.\n")

    plan = plan_projection("claude", config, home=home)
    assert plan.has_changes
    apply_projection_plan(plan, tmp_path / "backups")

    scoped_file = home / ".claude" / "rules" / "dotai-react-derived-state.md"
    universal_file = home / ".claude" / "rules" / "dotai-no-secrets.md"
    assert scoped_file.is_file()
    assert universal_file.is_file()

    scoped_text = scoped_file.read_text()
    assert scoped_text.startswith("---\npaths:\n  - \"*.tsx\"\n  - \"src/**/*.ts\"\n---\n")
    assert MANAGED_RULE_MARKER in scoped_text

    universal_text = universal_file.read_text()
    assert not universal_text.startswith("---")
    assert MANAGED_RULE_MARKER in universal_text

    # Skill symlink projected
    skill_link = home / ".claude" / "skills" / "release"
    assert skill_link.is_symlink()
    assert skill_link.resolve() == skill_dir.resolve()

    # Status is configured and second plan is idempotent
    status, _ = projection_status("claude", config, home=home)
    assert status == "configured"
    assert not plan_projection("claude", config, home=home).has_changes

    # Unmanaged user rule in ~/.claude/rules/ is never touched
    user_rule = home / ".claude" / "rules" / "dotai-custom-user.md"
    user_rule.write_text("# My hand-written rule\n")

    # Removing a dotai rule prunes only the dotai-managed projected file
    (config.global_rules_path / "no-secrets.md").unlink()
    status_after, _ = projection_status("claude", config, home=home)
    assert status_after == "out-of-sync"

    update_plan = plan_projection("claude", config, home=home)
    apply_projection_plan(update_plan, tmp_path / "backups")
    assert not universal_file.exists()
    assert user_rule.exists()


def test_codex_and_gemini_projection_preserve_existing_user_content(tmp_path):
    home = tmp_path / "home"
    (home / ".codex").mkdir(parents=True)
    codex_file = home / ".codex" / "AGENTS.md"
    codex_file.write_text("# My Codex Instructions\n\nKeep me.\n")

    config = _make_config(tmp_path)
    _write_rule(
        config.global_rules_path,
        "strict-types",
        "Strict Types",
        "Avoid Any in public APIs",
        "Always annotate public function signatures.",
    )

    plan = plan_projection("codex", config, home=home)
    backup = apply_projection_plan(plan, tmp_path / "backups")
    assert backup is not None
    content = codex_file.read_text()
    assert "# My Codex Instructions" in content
    assert "Keep me." in content
    assert PROJECTED_START_FMT.format(target="codex") in content
    assert "Strict Types" in content

    # Removal restores original content cleanly
    remove_plan = plan_projection_remove("codex", config, home=home)
    apply_projection_plan(remove_plan, tmp_path / "backups")
    assert codex_file.read_text() == "# My Codex Instructions\n\nKeep me.\n"


def test_cli_agent_setup_status_remove_all(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    config_dir = tmp_path / "config"
    config = _make_config(tmp_path)
    _write_rule(
        config.global_rules_path,
        "explicit-errors",
        "Explicit Errors",
        "Never swallow exceptions",
        "Always surface or log errors explicitly.",
    )

    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setattr(store, "_config_dir", config_dir)
    store.save_config(config)

    runner = CliRunner()
    preview = runner.invoke(app, ["agent", "setup", "all"])
    assert preview.exit_code == 0
    assert "Preview only" in preview.output

    applied = runner.invoke(app, ["agent", "setup", "all", "--apply"])
    assert applied.exit_code == 0
    assert (home / ".claude" / "rules" / "dotai-explicit-errors.md").is_file()
    assert (home / ".codex" / "AGENTS.md").is_file()
    assert (home / ".gemini" / "GEMINI.md").is_file()
    assert (home / ".agents" / "AGENTS.md").is_file()

    status = runner.invoke(app, ["agent", "status", "all"])
    assert status.exit_code == 0
    assert "configured" in status.output

    removed = runner.invoke(app, ["agent", "remove", "all", "--apply"])
    assert removed.exit_code == 0
    assert not (home / ".claude" / "rules" / "dotai-explicit-errors.md").exists()
    assert not (home / ".codex" / "AGENTS.md").exists()


def test_removing_one_shared_agent_preserves_shared_skills_until_last_removed(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    config = _make_config(tmp_path)
    _write_rule(
        config.global_rules_path,
        "strict-types",
        "Strict Types",
        "Avoid Any",
        "Always annotate public function signatures.",
    )
    skill_dir = config.global_skills_path / "deploy"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: deploy\ndescription: Deploy flow\n---\n\nDeploy.\n")

    for target in ("codex", "gemini"):
        apply_projection_plan(plan_projection(target, config, home=home), tmp_path / "backups")

    shared_skill = home / ".agents" / "skills" / "deploy"
    assert shared_skill.is_symlink()

    # Removing codex while gemini is still active keeps ~/.agents/skills/deploy intact
    apply_projection_plan(plan_projection_remove("codex", config, home=home), tmp_path / "backups")
    assert not (home / ".codex" / "AGENTS.md").exists()
    assert shared_skill.is_symlink()

    # Removing gemini (last active shared target) cleans up ~/.agents/skills/deploy
    apply_projection_plan(plan_projection_remove("gemini", config, home=home), tmp_path / "backups")
    assert not (home / ".gemini" / "GEMINI.md").exists()
    assert not shared_skill.exists()


def test_reversed_projection_markers_are_rejected(tmp_path):
    import pytest
    from dotai.projection import PROJECTED_END_FMT

    home = tmp_path / "home"
    (home / ".codex").mkdir(parents=True)
    codex_file = home / ".codex" / "AGENTS.md"
    codex_file.write_text(
        f"{PROJECTED_END_FMT.format(target='codex')}\n"
        "User content\n"
        f"{PROJECTED_START_FMT.format(target='codex')}\n"
    )
    config = _make_config(tmp_path)
    _write_rule(
        config.global_rules_path,
        "strict-types",
        "Strict Types",
        "Avoid Any",
        "Always annotate public function signatures.",
    )

    status, _ = projection_status("codex", config, home=home)
    assert status == "invalid"
    with pytest.raises(ValueError, match="reversed"):
        plan_projection("codex", config, home=home)


def test_claude_projection_avoids_reserved_notes_filename_collision(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    config = _make_config(tmp_path)
    (config.global_ai_dir / "rules.md").write_text("# Global Notes\n\nKeep PRs focused.\n")
    _write_rule(
        config.global_rules_path,
        "global-notes",
        "Global Notes",
        "Explicit user rule named global-notes",
        "Never drop user rule files when global notes also exist.",
    )

    plan = plan_projection("claude", config, home=home)
    apply_projection_plan(plan, tmp_path / "backups")

    rule_file = home / ".claude" / "rules" / "dotai-global-notes.md"
    notes_file = home / ".claude" / "rules" / "dotai--global-notes.md"
    assert rule_file.is_file()
    assert notes_file.is_file()
    assert "Explicit user rule named global-notes" in rule_file.read_text()
    assert "Keep PRs focused." in notes_file.read_text()
