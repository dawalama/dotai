"""Tests for harvesting candidate durable rules from native agent auto-memory."""

from pathlib import Path

from typer.testing import CliRunner

from dotai import store
from dotai.cli import app
from dotai.harvest import harvest_claude_memory
from dotai.models import GlobalConfig
from dotai.rules import create_rule_from_directive, load_rules_from_dir


def test_harvest_claude_memory_extracts_frontmatter_and_bullets_and_dedupes(tmp_path):
    home = tmp_path / "home"
    mem_dir = home / ".claude" / "projects" / "-Users-dev-myapp" / "memory"
    mem_dir.mkdir(parents=True)

    (mem_dir / "MEMORY.md").write_text(
        "# Memory\n\n"
        "- [feedback_tests.md](feedback_tests.md) — Testing rule\n"
        "- Always run pytest with -q before pushing changes to main.\n"
        "- short\n"
    )
    (mem_dir / "feedback_tests.md").write_text(
        "---\n"
        "name: No Mocked Database\n"
        "description: Use real Postgres in integration tests\n"
        "type: feedback\n"
        "---\n\n"
        "Never mock the database in integration tests; use the local test container.\n"
    )

    ai_dir = tmp_path / ".ai"
    (ai_dir / "rules").mkdir(parents=True)
    config = GlobalConfig(global_ai_dir=ai_dir)

    candidates = harvest_claude_memory(config, home=home)
    assert len(candidates) == 2
    titles = {c.title for c in candidates}
    assert "No Mocked Database" in titles
    assert any("pytest" in c.body for c in candidates)

    # Once promoted into ~/.ai/rules/, it is filtered out by default
    create_rule_from_directive(
        name="No Mocked Database",
        dest_dir=config.global_rules_path,
        directive="Never mock the database in integration tests; use the local test container.",
        description="Use real Postgres in integration tests",
    )
    remaining = harvest_claude_memory(config, home=home)
    assert len(remaining) == 1
    assert "pytest" in remaining[0].body


def test_harvest_cli_promote(tmp_path, monkeypatch):
    home = tmp_path / "home"
    mem_dir = home / ".claude" / "projects" / "-Users-dev-api" / "memory"
    mem_dir.mkdir(parents=True)
    (mem_dir / "feedback_auth.md").write_text(
        "---\n"
        "name: Bearer Token Prefix\n"
        "type: feedback\n"
        "---\n\n"
        "Always prepend 'Bearer ' to API authorization headers.\n"
    )

    ai_dir = tmp_path / ".ai"
    (ai_dir / "rules").mkdir(parents=True)
    config = GlobalConfig(global_ai_dir=ai_dir)
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setattr(store, "_config_dir", tmp_path / "config")
    store.save_config(config)

    runner = CliRunner()
    res = runner.invoke(app, ["harvest", "claude"])
    assert res.exit_code == 0
    assert "Bearer Token Prefix" in res.output

    dry = runner.invoke(app, ["harvest", "claude", "--promote", "1", "--dry-run"])
    assert dry.exit_code == 0
    assert "Dry run" in dry.output
    assert len(load_rules_from_dir(config.global_rules_path)) == 0

    promoted = runner.invoke(app, ["harvest", "claude", "--promote", "1"])
    assert promoted.exit_code == 0
    rules = load_rules_from_dir(config.global_rules_path)
    assert len(rules) == 1
    assert rules[0].id == "bearer-token-prefix"


def test_harvest_ignores_empty_token_existing_rules(tmp_path):
    home = tmp_path / "home"
    mem_dir = home / ".claude" / "projects" / "-Users-dev-app" / "memory"
    mem_dir.mkdir(parents=True)
    (mem_dir / "feedback_real.md").write_text(
        "---\nname: Use Ruff Format\ntype: feedback\n---\n\n"
        "Always run ruff format before committing Python changes.\n"
    )

    ai_dir = tmp_path / ".ai"
    (ai_dir / "rules").mkdir(parents=True)
    # Rule whose name/description/body normalize to zero tokens (all stop words / short words)
    (ai_dir / "rules" / "tiny.md").write_text("---\nname: a\ndescription: to\n---\n\nin on at\n")
    config = GlobalConfig(global_ai_dir=ai_dir)

    candidates = harvest_claude_memory(config, home=home)
    assert len(candidates) == 1
    assert candidates[0].title == "Use Ruff Format"
