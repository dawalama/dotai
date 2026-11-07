"""Tests for dotai init and seed-free fresh installation."""

from pathlib import Path
from typer.testing import CliRunner

from dotai.cli import app
from dotai import store
from dotai.models import GlobalConfig


def test_init_global_fresh_installation_has_no_generic_seeds(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    monkeypatch.setattr(store, "_config_dir", tmp_path / "config")

    result = CliRunner().invoke(app, ["init"])
    assert result.exit_code == 0

    ai_dir = fake_home / ".ai"
    assert ai_dir.exists()
    assert (ai_dir / "rules.md").exists()
    assert (ai_dir / "rules").is_dir()
    assert (ai_dir / "skills").is_dir()
    assert (ai_dir / "preferences").is_dir()
    assert (ai_dir / "tools").is_dir()

    # Crucial acceptance criterion: No mandatory generic workflow/persona library seeded
    skill_files = list((ai_dir / "skills").glob("*"))
    assert len(skill_files) == 0, f"Expected 0 seed skills, found: {skill_files}"

    roles_dir = ai_dir / "roles"
    if roles_dir.exists():
        role_files = list(roles_dir.glob("*"))
        assert len(role_files) == 0, f"Expected 0 seed roles, found: {role_files}"


def test_init_preserves_existing_user_content(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    ai_dir = fake_home / ".ai"
    ai_dir.mkdir(parents=True)
    custom_rule = ai_dir / "rules" / "custom.md"
    custom_rule.parent.mkdir(parents=True)
    custom_rule.write_text("My custom rule")

    custom_skill = ai_dir / "skills" / "deploy" / "SKILL.md"
    custom_skill.parent.mkdir(parents=True)
    custom_skill.write_text("My custom skill")

    monkeypatch.setattr(Path, "home", lambda: fake_home)
    monkeypatch.setattr(store, "_config_dir", tmp_path / "config")

    result = CliRunner().invoke(app, ["init"])
    assert result.exit_code == 0

    # Custom content must survive untouched
    assert custom_rule.exists()
    assert custom_rule.read_text() == "My custom rule"
    assert custom_skill.exists()
    assert custom_skill.read_text() == "My custom skill"


def test_init_project(tmp_path, monkeypatch):
    proj_dir = tmp_path / "my-project"
    proj_dir.mkdir()
    config_dir = tmp_path / "config"
    monkeypatch.setattr(store, "_config_dir", config_dir)

    result = CliRunner().invoke(app, ["init", str(proj_dir)])
    assert result.exit_code == 0

    ai_dir = proj_dir / ".ai"
    assert ai_dir.exists()
    assert (ai_dir / "rules.md").exists()
    assert (ai_dir / "rules").is_dir()
    assert (ai_dir / "skills").is_dir()
    assert (ai_dir / "preferences").is_dir()
