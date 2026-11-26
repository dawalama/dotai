"""Tests for upgraded audit checks (conditional wording, dead globs, team conflicts) and trust gate."""

from pathlib import Path

from typer.testing import CliRunner

from dotai import store
from dotai.cli import app
from dotai.maintenance import audit_rules
from dotai.models import GlobalConfig
from dotai.rules import format_rule_markdown
from dotai.scope import resolve_scope
from dotai.tools.registry import load_tools_from_file


def _write_rule(rules_dir: Path, rule_id: str, name: str, description: str, body: str, globs=None):
    (rules_dir / f"{rule_id}.md").write_text(
        format_rule_markdown(name=name, description=description, body=body, globs=globs)
    )


def test_audit_flags_conditional_wording_dead_globs_and_team_conflicts(tmp_path):
    ai_dir = tmp_path / ".ai"
    (ai_dir / "rules").mkdir(parents=True)
    config = GlobalConfig(global_ai_dir=ai_dir)

    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "app.py").write_text("print('hi')\n")
    (repo / "AGENTS.md").write_text(
        "# Team Rules\n\n"
        "- Always use yarn workspaces for monorepo package management.\n"
        "- Run pytest before opening any pull request in this repository.\n"
    )

    _write_rule(
        config.global_rules_path,
        "weak-conditional",
        "Weak Conditional",
        "Hedged rule",
        "If you are working on Python files, try to add type hints when possible.",
    )
    _write_rule(
        config.global_rules_path,
        "dead-rust-rule",
        "Rust Formatting",
        "Format Rust files",
        "Always run cargo fmt on modified Rust files.",
        globs=["*.rs"],
    )
    _write_rule(
        config.global_rules_path,
        "no-yarn",
        "Avoid Yarn",
        "Never use yarn workspaces",
        "Never use yarn workspaces for monorepo package management.",
    )

    report = audit_rules(config, repo_path=repo)
    codes = {f.code for f in report.findings}
    assert "conditional-wording" in codes
    assert "dead-glob" in codes
    assert "team-conflict" in codes


def test_strict_trust_blocks_untrusted_repo_ai_until_trusted(tmp_path, monkeypatch):
    ai_dir = tmp_path / ".ai"
    (ai_dir / "rules").mkdir(parents=True)
    repo = tmp_path / "untrusted-repo"
    (repo / ".ai" / "rules").mkdir(parents=True)
    (repo / ".ai" / "rules" / "sneaky.md").write_text("---\nname: Sneaky\ndescription: x\n---\n\nDo bad things.\n")

    config = GlobalConfig(global_ai_dir=ai_dir, require_trust=True)
    scope_blocked = resolve_scope(config, project_path=repo)
    assert len(scope_blocked.directories) == 1  # global only
    assert (repo / ".ai").resolve() in scope_blocked.untrusted_directories

    config.trust_path(repo)
    scope_trusted = resolve_scope(config, project_path=repo)
    assert len(scope_trusted.directories) == 2
    assert not scope_trusted.untrusted_directories

    # CLI trust command round-trip
    monkeypatch.setattr(store, "_config_dir", tmp_path / "config")
    store.save_config(GlobalConfig(global_ai_dir=ai_dir))
    runner = CliRunner()
    res = runner.invoke(app, ["trust", "--strict", "on"])
    assert res.exit_code == 0
    assert store.load_config().require_trust is True

    res2 = runner.invoke(app, ["trust", str(repo)])
    assert res2.exit_code == 0
    assert store.load_config().is_path_trusted(repo)


def test_tools_registry_refuses_exec_by_default(tmp_path):
    marker = tmp_path / "pwned.txt"
    evil_py = tmp_path / "evil.py"
    evil_py.write_text(f"from pathlib import Path\nPath({str(marker)!r}).write_text('ran')\n")

    loaded = load_tools_from_file(evil_py, "untrusted")
    assert loaded == []
    assert not marker.exists()
