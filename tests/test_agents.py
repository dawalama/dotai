"""Tests for user-level agent adapter planning and application."""

import pytest

from dotai.agents import (
    ADAPTER_MARKER_END,
    ADAPTER_MARKER_START,
    apply_agent_plan,
    claude_adapter_status,
    plan_claude_remove,
    plan_claude_setup,
)


def test_setup_creates_new_user_memory(tmp_path):
    path = tmp_path / ".claude" / "CLAUDE.md"

    plan = plan_claude_setup(path, command="/opt/dotai/bin/dotai")

    assert plan.action == "create"
    assert ADAPTER_MARKER_START in plan.content
    assert "/opt/dotai/bin/dotai context --agent claude --path ." in plan.content
    assert "Repository and organization instructions are authoritative" in plan.content
    assert "you MUST run dotai again" in plan.content


def test_setup_preserves_existing_personal_memory(tmp_path):
    path = tmp_path / "CLAUDE.md"
    path.write_text("# My Memory\n\nKeep this.\n")

    plan = plan_claude_setup(path)
    apply_agent_plan(plan, tmp_path / "backups")

    result = path.read_text()
    assert "# My Memory" in result
    assert "Keep this." in result
    assert result.count(ADAPTER_MARKER_START) == 1
    assert any((tmp_path / "backups").iterdir())


def test_setup_shell_quotes_executable_path(tmp_path):
    path = tmp_path / "CLAUDE.md"

    plan = plan_claude_setup(path, command="/Applications/dot ai/bin/dotai")

    assert "'/Applications/dot ai/bin/dotai' context" in plan.content


def test_setup_is_idempotent(tmp_path):
    path = tmp_path / "CLAUDE.md"
    first = plan_claude_setup(path)
    apply_agent_plan(first, tmp_path / "backups")

    second = plan_claude_setup(path)

    assert second.action == "none"


def test_remove_preserves_non_dotai_content(tmp_path):
    path = tmp_path / "CLAUDE.md"
    path.write_text("# Personal\n")
    apply_agent_plan(plan_claude_setup(path), tmp_path / "backups")

    removal = plan_claude_remove(path)
    apply_agent_plan(removal, tmp_path / "backups")

    assert path.read_text() == "# Personal\n"


def test_remove_deletes_dotai_only_file(tmp_path):
    path = tmp_path / "CLAUDE.md"
    apply_agent_plan(plan_claude_setup(path), tmp_path / "backups")

    removal = plan_claude_remove(path)
    assert removal.action == "remove"
    apply_agent_plan(removal, tmp_path / "backups")

    assert not path.exists()


def test_status_reports_incomplete_markers(tmp_path):
    path = tmp_path / "CLAUDE.md"
    path.write_text(f"{ADAPTER_MARKER_START}\nbroken\n")

    assert claude_adapter_status(path)[0] == "invalid"
    with pytest.raises(ValueError, match="incomplete"):
        plan_claude_setup(path)


def test_symlink_is_never_modified(tmp_path):
    outside = tmp_path / "outside.md"
    outside.write_text("Do not touch\n")
    path = tmp_path / "CLAUDE.md"
    path.symlink_to(outside)

    with pytest.raises(ValueError, match="symlinked"):
        plan_claude_setup(path)
    assert outside.read_text() == "Do not touch\n"


def test_apply_rechecks_for_symlink_swap(tmp_path):
    path = tmp_path / "CLAUDE.md"
    plan = plan_claude_setup(path)
    outside = tmp_path / "outside.md"
    outside.write_text("Do not touch\n")
    path.symlink_to(outside)

    with pytest.raises(ValueError, match="symlinked"):
        apply_agent_plan(plan, tmp_path / "backups")
    assert outside.read_text() == "Do not touch\n"
