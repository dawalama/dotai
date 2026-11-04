"""Regression coverage for shared context/export scope and precedence."""

from pathlib import Path
import subprocess

import pytest
from typer.testing import CliRunner

from dotai.catalog import load_catalog
from dotai.cli import app
from dotai.context import resolve_context
from dotai.models import GlobalConfig, ProjectConfig
from dotai.preferences import create_preference_pack, save_active_pack_ids
from dotai.rules import format_rule_markdown
from dotai.sync import generate_primer


def write_rule(ai, body, *, enabled=True, globs=None):
    directory = ai / "rules"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "shared.md").write_text(format_rule_markdown(
        "Shared", "Application boundary", body, enabled=enabled, globs=globs,
    ))


@pytest.mark.parametrize("compact", [False, True])
def test_primer_and_context_use_local_override(ai_dir, config, tmp_path, compact):
    repo = tmp_path / "repo"
    write_rule(ai_dir, "GLOBAL DIRECTIVE")
    write_rule(repo / ".ai", "PROJECT DIRECTIVE")

    primer = generate_primer(config, project_path=repo, compact=compact)
    resolved = resolve_context(config, repo).to_prompt()

    for output in (primer, resolved):
        assert "PROJECT DIRECTIVE" in output
        assert "GLOBAL DIRECTIVE" not in output


def test_disabled_local_override_masks_inherited_rule(ai_dir, config, tmp_path):
    repo = tmp_path / "repo"
    write_rule(ai_dir, "GLOBAL DIRECTIVE")
    write_rule(repo / ".ai", "DISABLED DIRECTIVE", enabled=False)

    assert load_catalog(config, project_path=repo).rules == []
    assert "GLOBAL DIRECTIVE" not in generate_primer(config, project_path=repo)
    assert "GLOBAL DIRECTIVE" not in resolve_context(config, repo).to_prompt()


@pytest.mark.parametrize("project_name", ["repo", "global"])
def test_registered_disabled_list_skips_global_but_keeps_local_override(ai_dir, tmp_path, project_name):
    repo = tmp_path / "repo"
    repo.mkdir()
    write_rule(ai_dir, "GLOBAL DIRECTIVE")
    config = GlobalConfig(global_ai_dir=ai_dir, projects=[
        ProjectConfig(name=project_name, path=repo, disabled_rules=["shared"]),
    ])
    assert load_catalog(config, project_path=repo).rules == []
    write_rule(repo / ".ai", "PROJECT DIRECTIVE")
    assert [r.body for r in load_catalog(config, project_path=repo).rules] == ["PROJECT DIRECTIVE"]


def test_unrelated_projects_are_not_read_or_exported(ai_dir, tmp_path):
    other = tmp_path / "other"
    roles = other / ".ai/roles"
    roles.mkdir(parents=True)
    (roles / "broken.md").write_bytes(b"\xff")  # Reading this would fail.
    config = GlobalConfig(global_ai_dir=ai_dir, projects=[ProjectConfig(name="other", path=other)])
    repo = tmp_path / "repo"
    repo.mkdir()

    assert load_catalog(config, project_path=repo).roles == []
    assert "broken" not in generate_primer(config, project_path=repo)
    assert "broken" not in generate_primer(config)  # Global-only export.
    assert resolve_context(config, repo).role is None


def test_nested_custom_project_scope_includes_ancestors_and_preferences(ai_dir, tmp_path):
    repo = tmp_path / "repo"
    nested = repo / "packages/api"
    nested.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    custom = repo / "config/judgment"
    write_rule(custom, "ROOT DIRECTIVE")
    write_rule(nested / ".ai", "NESTED DIRECTIVE")
    (custom / "rules.md").write_text("ROOT NOTES")
    create_preference_pack(custom / "preferences", "Taste", pack_id="taste", body="ROOT TASTE")
    save_active_pack_ids(custom, ["taste"])
    config = GlobalConfig(global_ai_dir=ai_dir, projects=[
        ProjectConfig(name="repo", path=repo, ai_dir=Path("config/judgment")),
    ])

    resolved = resolve_context(config, nested)
    primer = generate_primer(config, project_path=nested, compact=True)
    assert [r.body for r in resolved.rules] == ["NESTED DIRECTIVE"]
    assert "ROOT NOTES" in resolved.to_prompt()
    assert "ROOT TASTE" in resolved.to_prompt()
    assert "NESTED DIRECTIVE" in primer and "ROOT DIRECTIVE" not in primer
    assert load_catalog(config, project_path=nested).scope.project_name == "repo"


def test_unregistered_git_scope_inherits_root_but_stops_at_repository(ai_dir, tmp_path):
    outside = tmp_path / "outside"
    write_rule(outside / ".ai", "OUTSIDE DIRECTIVE")
    repo = outside / "repo"
    nested = repo / "src"
    nested.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    write_rule(repo / ".ai", "ROOT DIRECTIVE")

    resolved = resolve_context(config=GlobalConfig(global_ai_dir=ai_dir), project_path=nested)
    assert [r.body for r in resolved.rules] == ["ROOT DIRECTIVE"]


def test_explicit_project_rejects_unrelated_path(ai_dir, tmp_path):
    config = GlobalConfig(global_ai_dir=ai_dir, projects=[
        ProjectConfig(name="other", path=tmp_path / "other"),
    ])
    with pytest.raises(ValueError, match="outside project"):
        load_catalog(config, "other", tmp_path / "repo")


def test_scope_merges_roles_and_skills_before_selection(ai_dir, config, tmp_path):
    repo = tmp_path / "repo"
    for base, label in ((ai_dir, "GLOBAL"), (repo / ".ai", "LOCAL")):
        for kind in ("roles", "skills"):
            (base / kind).mkdir(parents=True, exist_ok=True)
            (base / kind / "shared.md").write_text(
                f"---\nname: Shared\ntrigger: /run_shared\n---\n{label} {kind}\n"
            )
    resolved = resolve_context(config, repo, skill_id="run_shared", role_id="shared")
    assert "LOCAL skills" in resolved.to_prompt()
    assert "LOCAL roles" in resolved.to_prompt()
    assert "GLOBAL" not in resolved.to_prompt()


def test_cli_context_and_primer_infer_registered_ancestor(ai_dir, tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    nested = repo / "src"
    nested.mkdir(parents=True)
    write_rule(repo / "judgment", "CUSTOM DIRECTIVE")
    config = GlobalConfig(global_ai_dir=ai_dir, projects=[
        ProjectConfig(name="repo", path=repo, ai_dir=Path("judgment")),
    ])
    monkeypatch.setattr("dotai.store.load_config", lambda: config)
    runner = CliRunner()
    for command in ("context", "primer"):
        result = runner.invoke(app, [command, "--path", str(nested)])
        assert result.exit_code == 0, result.output
        assert "CUSTOM DIRECTIVE" in result.output


def test_compact_primer_growth_is_bounded_for_unrelated_rules(ai_dir, config, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    def populate(start, end):
        for n in range(start, end):
            (ai_dir / f"rules/rule-{n}.md").write_text(format_rule_markdown(
                f"Rule {n}", "Unrelated instruction", "UNRELATED BODY", globs=[f"unrelated-{n}/*.tsx"],
            ))
    populate(0, 10)
    small = generate_primer(config, project_path=repo, compact=True)
    populate(10, 1000)
    large = generate_primer(config, project_path=repo, compact=True)
    resolved = resolve_context(config, repo, files=["src/api.py"])

    assert "1000 file-scoped rules" in large
    assert "UNRELATED BODY" not in large
    assert len(large) - len(small) < 10
    assert resolved.rules == []


def test_registered_child_keeps_parent_custom_knowledge(ai_dir, tmp_path):
    repo = tmp_path / "repo"
    child = repo / "packages/api"
    child.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    custom = repo / "judgment"
    write_rule(custom, "PARENT DIRECTIVE")
    write_rule(repo / ".ai", "WRONG DIRECTORY")
    (custom / "rules.md").write_text("PARENT NOTES")
    create_preference_pack(custom / "preferences", "Root Taste", pack_id="root", body="PARENT TASTE")
    save_active_pack_ids(custom, ["root"])
    config = GlobalConfig(global_ai_dir=ai_dir, projects=[
        ProjectConfig(name="root", path=repo, ai_dir=Path("judgment")),
        ProjectConfig(name="api", path=child),
    ])

    for output in (
        resolve_context(config, child).to_prompt(),
        generate_primer(config, project_path=child),
    ):
        assert "PARENT DIRECTIVE" in output
        assert "PARENT NOTES" in output
        assert "PARENT TASTE" in output
        assert "WRONG DIRECTORY" not in output


@pytest.mark.parametrize("path_kind", ["root-relative", "cwd-relative", "absolute"])
def test_file_globs_follow_rule_owner_from_nested_working_directories(ai_dir, tmp_path, path_kind):
    repo = tmp_path / "repo"
    nested = repo / "packages/api"
    nested.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    write_rule(repo / ".ai", "ROOT FILE DIRECTIVE", globs=["packages/api/*.py"])
    local_rules = nested / ".ai/rules"
    local_rules.mkdir(parents=True)
    (local_rules / "local.md").write_text(format_rule_markdown(
        "Local", "API tests", "LOCAL FILE DIRECTIVE", globs=["tests/*.py"],
    ))
    config = GlobalConfig(global_ai_dir=ai_dir)
    target = nested / "tests/test_handler.py"
    invocation = repo if path_kind == "root-relative" else nested
    filename = str(target) if path_kind == "absolute" else str(target.relative_to(invocation))

    resolved = resolve_context(config, invocation, files=[filename])
    assert "ROOT FILE DIRECTIVE" in resolved.to_prompt()
    if invocation == nested:
        assert "LOCAL FILE DIRECTIVE" in resolved.to_prompt()


def test_scoped_rules_do_not_match_files_outside_their_owner(ai_dir, tmp_path):
    repo = tmp_path / "repo"
    write_rule(repo / ".ai", "PROJECT DIRECTIVE", globs=["*.py"])
    resolved = resolve_context(GlobalConfig(global_ai_dir=ai_dir), repo, files=[str(tmp_path / "outside.py")])
    assert resolved.rules == []


def test_scoped_globs_match_logical_symlink_paths(ai_dir, tmp_path):
    repo = tmp_path / "repo"
    write_rule(repo / ".ai", "PROJECT DIRECTIVE", globs=["*.py"])
    outside = tmp_path / "outside.py"
    outside.write_text("pass\n")
    (repo / "linked.py").symlink_to(outside)
    resolved = resolve_context(GlobalConfig(global_ai_dir=ai_dir), repo, files=["./linked.py"])
    assert [r.id for r in resolved.rules] == ["shared"]
