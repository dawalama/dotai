"""Tests for local deterministic resolution insights."""

import json

import pytest
from typer.testing import CliRunner

from dotai.cli import app
from dotai.context import resolve_context, save_resolution_receipt
from dotai.insights import build_insights, load_receipt_history


def test_insights_aggregate_selection_and_exposure(
    ai_dir, config, sample_rule_file, sample_skill_file, sample_role_file
):
    receipts_dir = ai_dir.parent / "receipts"
    first = resolve_context(
        config,
        ai_dir.parent,
        task="Review the changes",
        files=["src/app.ts"],
        skill_id="run_test",
    )
    second = resolve_context(config, ai_dir.parent, task="Explain the project")
    save_resolution_receipt(first, "claude", receipts_dir)
    save_resolution_receipt(second, "claude", receipts_dir)

    report = build_insights(config, receipts_dir)

    assert report.resolutions == 2
    assert report.complete == 2
    rule = next(item for item in report.items if item.item_id == "no-console-log")
    assert rule.selected == 1
    skill = next(item for item in report.items if item.item_id == "test-skill")
    assert skill.selected == 1
    assert "test-reviewer" not in report.unused["role"]


def test_history_falls_back_to_legacy_latest_receipt(ai_dir):
    receipts_dir = ai_dir.parent / "receipts"
    receipts_dir.mkdir()
    (receipts_dir / "claude.json").write_text(json.dumps({
        "agent": "claude",
        "resolved_at": "2026-01-01T00:00:00+00:00",
        "project_path": str(ai_dir.parent),
    }))

    history = load_receipt_history(receipts_dir)

    assert len(history) == 1
    assert history[0]["agent"] == "claude"


def test_insights_json_command(ai_dir, config, sample_rule_file, monkeypatch):
    from dotai import store

    receipts_dir = ai_dir.parent / "config" / "receipts"
    resolved = resolve_context(config, ai_dir.parent, files=["src/app.ts"])
    save_resolution_receipt(resolved, "claude", receipts_dir)
    monkeypatch.setattr(store, "_config_dir", ai_dir.parent / "config")
    monkeypatch.setattr(store, "load_config", lambda: config)

    result = CliRunner().invoke(app, ["insights", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["resolutions"] == 1
    assert payload["items"][0]["kind"] == "rule"


def test_history_rejects_unsafe_agent_id(ai_dir):
    with pytest.raises(ValueError, match="Invalid agent"):
        load_receipt_history(ai_dir.parent / "receipts", "../outside")
