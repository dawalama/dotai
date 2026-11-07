"""Tests for lossless migration of legacy dotai skills and roles."""

import json
from pathlib import Path
from typer.testing import CliRunner

from dotai.cli import app
from dotai.models import GlobalConfig, ProjectConfig
from dotai.migration import apply_migration, plan_migration


def test_plan_migration_detects_legacy_folder_skill(tmp_path):
    skills_dir = tmp_path / "skills"
    deploy_dir = skills_dir / "deploy"
    deploy_dir.mkdir(parents=True)
    main_content = "---\nname: Deploy\ntrigger: /run_deploy\ncategory: deployment\nallowed-tools: Bash\n---\n\n## Custom Steps\n\n1. Step one\n2. Step two\n"
    (deploy_dir / "main.md").write_text(main_content)

    config = GlobalConfig(global_ai_dir=tmp_path)
    plan = plan_migration(config)

    assert plan.has_changes is True
    assert len(plan.actions) == 1
    action = plan.actions[0]
    assert action.kind == "skill"
    assert action.source_path == deploy_dir / "main.md"
    assert action.target_path == deploy_dir / "SKILL.md"
    assert any("allowed-tools" in w for w in action.warnings)


def test_plan_migration_detects_legacy_role(tmp_path):
    roles_dir = tmp_path / "roles"
    roles_dir.mkdir(parents=True)
    role_content = "---\nname: Security Reviewer\ndescription: Audit code\ntags: security\n---\n\nYou are a security expert.\n\n## Principles\n- Principle 1\n\n## Anti-patterns\n- Pattern 1\n"
    (roles_dir / "sec-rev.md").write_text(role_content)

    config = GlobalConfig(global_ai_dir=tmp_path)
    plan = plan_migration(config)

    assert plan.has_changes is True
    assert len(plan.actions) == 1
    action = plan.actions[0]
    assert action.kind == "role"
    assert action.source_path == roles_dir / "sec-rev.md"
    assert action.target_path == tmp_path / "skills" / "sec-rev" / "SKILL.md"


def test_apply_migration_lossless_execution_and_backups(tmp_path):
    ai_dir = tmp_path / ".ai"
    skills_dir = ai_dir / "skills"
    deploy_dir = skills_dir / "deploy"
    deploy_dir.mkdir(parents=True)
    main_content = "---\nname: Deploy\ntrigger: /run_deploy\ncategory: deployment\n---\n\n## Custom Details\n\nPreserve this exact text verbatim.\n"
    (deploy_dir / "main.md").write_text(main_content)

    roles_dir = ai_dir / "roles"
    roles_dir.mkdir(parents=True)
    role_content = "---\nname: Systems Architect\ndescription: Design systems\ntags: arch\n---\n\nStaff architect persona.\n\n## Principles\n- Keep it simple\n"
    (roles_dir / "architect.md").write_text(role_content)

    config = GlobalConfig(global_ai_dir=ai_dir)
    plan = plan_migration(config)
    assert len(plan.actions) == 2

    # Test dry-run leaves disk unchanged
    dry_applied = apply_migration(plan, backup_root=tmp_path / "backups", dry_run=True)
    assert len(dry_applied) == 2
    assert (deploy_dir / "main.md").exists()
    assert not (deploy_dir / "SKILL.md").exists()
    assert (roles_dir / "architect.md").exists()

    # Apply migration
    applied = apply_migration(plan, backup_root=tmp_path / "backups", dry_run=False)
    assert len(applied) == 2

    # Verify skill migration
    assert (deploy_dir / "SKILL.md").exists()
    assert (deploy_dir / "SKILL.md").read_text() == main_content
    assert not (deploy_dir / "main.md").exists()
    assert (deploy_dir / ".dotai-metadata.json").exists()
    meta = json.loads((deploy_dir / ".dotai-metadata.json").read_text())
    assert meta["category"] == "deployment"
    assert meta["trigger"] == "/run_deploy"

    # Verify role migration
    target_role_skill = skills_dir / "architect" / "SKILL.md"
    assert target_role_skill.exists()
    role_skill_text = target_role_skill.read_text()
    assert "Staff architect persona." in role_skill_text
    assert "Keep it simple" in role_skill_text
    assert "tags: [arch, role, perspective, migrated]" in role_skill_text
    assert not (roles_dir / "architect.md").exists()

    # Verify backups exist
    backups = list((tmp_path / "backups").glob("migration-*"))
    assert len(backups) == 1
    assert (backups[0] / "main.md").exists()
    assert (backups[0] / "architect.md").exists()


def test_migrate_cli_command(tmp_path, monkeypatch):
    from dotai import store

    ai_dir = tmp_path / ".ai"
    skills_dir = ai_dir / "skills" / "my-skill"
    skills_dir.mkdir(parents=True)
    (skills_dir / "main.md").write_text("---\nname: My Skill\n---\n\nHello\n")

    config = GlobalConfig(global_ai_dir=ai_dir)
    monkeypatch.setattr(store, "_config_dir", tmp_path / "config")
    monkeypatch.setattr(store, "load_config", lambda: config)

    # Dry-run CLI
    result = CliRunner().invoke(app, ["migrate", "--dry-run"])
    assert result.exit_code == 0
    assert "Planned Migrations" in result.output
    assert "Dry-run:" in result.output
    assert not (skills_dir / "SKILL.md").exists()

    # Apply CLI
    result_apply = CliRunner().invoke(app, ["migrate"])
    assert result_apply.exit_code == 0
    assert "Successfully migrated 1 item(s)" in result_apply.output
    assert (skills_dir / "SKILL.md").exists()
    assert not (skills_dir / "main.md").exists()
