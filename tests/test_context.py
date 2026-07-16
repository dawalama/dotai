"""Tests for deterministic, on-demand context resolution."""

import json

import pytest

from dotai.context import (
    load_resolution_receipt,
    resolve_context,
    save_resolution_receipt,
)
from dotai.models import GlobalConfig, ProjectConfig
from dotai.preferences import create_preference_pack, save_active_pack_ids


def test_universal_rules_are_summaries_not_full_bodies(ai_dir, config):
    (ai_dir / "rules" / "safety.md").write_text(
        "---\nname: Safety\ndescription: Never expose secrets\nglobs: *\ntags: security\n---\n"
        "FULL SECRET HANDLING PROCEDURE\n"
    )

    resolved = resolve_context(config, ai_dir.parent)

    assert [rule.id for rule in resolved.rule_summaries] == ["safety"]
    assert resolved.rules == []
    prompt = resolved.to_prompt()
    assert "Never expose secrets" in prompt
    assert "FULL SECRET HANDLING PROCEDURE" not in prompt


def test_file_glob_expands_matching_rule(ai_dir, config, sample_rule_file):
    resolved = resolve_context(config, ai_dir.parent, files=["src/app.tsx"])

    assert [rule.id for rule in resolved.rules] == ["no-console-log"]
    assert "file `src/app.tsx` matches `*.tsx`" in resolved.to_prompt()
    assert "Remove all `console.log`" in resolved.to_prompt()


def test_context_tag_expands_rule(ai_dir, config):
    (ai_dir / "rules" / "credentials.md").write_text(
        "---\nname: Credentials\ndescription: Protect credentials\nglobs: *\ntags: auth, security\n---\n"
        "Never log credentials.\n"
    )

    resolved = resolve_context(config, ai_dir.parent, contexts=["auth"])

    assert [rule.id for rule in resolved.rules] == ["credentials"]
    assert "rule tag matches context: auth" in resolved.to_prompt()


def test_only_active_preferences_in_requested_domain(ai_dir, config):
    prefs = ai_dir / "preferences"
    prefs.mkdir()
    create_preference_pack(
        prefs, "CLI Taste", pack_id="cli-taste", domain="cli", body="Prefer Rich tables."
    )
    create_preference_pack(
        prefs, "Design Taste", pack_id="design-taste", domain="design", body="Use quiet borders."
    )
    save_active_pack_ids(ai_dir, ["cli-taste", "design-taste"])

    resolved = resolve_context(config, ai_dir.parent, domains=["cli"])

    assert [pack.id for pack in resolved.preferences] == ["cli-taste"]
    assert "Prefer Rich tables." in resolved.to_prompt()
    assert "Use quiet borders." not in resolved.to_prompt()


def test_explicit_skill_loads_its_default_role(
    ai_dir, tmp_path, sample_skill_file, sample_role_file
):
    config = GlobalConfig(
        global_ai_dir=ai_dir,
        projects=[ProjectConfig(name="repo", path=tmp_path)],
    )

    resolved = resolve_context(config, tmp_path, "repo", skill_id="run_test")

    assert resolved.skill and resolved.skill.id == "test-skill"
    assert resolved.role and resolved.role.id == "test-reviewer"
    assert "Run the project test suite" in resolved.to_prompt()
    assert "You are a test reviewer" in resolved.to_prompt()


def test_task_routes_unambiguous_skill_alias(
    ai_dir, tmp_path, sample_skill_file, sample_role_file
):
    config = GlobalConfig(
        global_ai_dir=ai_dir,
        projects=[ProjectConfig(name="repo", path=tmp_path)],
    )

    resolved = resolve_context(
        config, tmp_path, "repo", task="Please run_test before we ship"
    )

    assert resolved.skill and resolved.skill.id == "test-skill"
    assert "unambiguous task alias" in resolved.reason_for("skill", "test-skill")
    assert resolved.provisional is True
    assert "Provisional Resolution — Files Required" in resolved.to_prompt()


def test_file_aware_skill_resolution_is_complete(
    ai_dir, tmp_path, sample_skill_file, sample_role_file
):
    config = GlobalConfig(
        global_ai_dir=ai_dir,
        projects=[ProjectConfig(name="repo", path=tmp_path)],
    )

    resolved = resolve_context(
        config,
        tmp_path,
        "repo",
        task="Please run_test",
        files=["tests/test_api.py"],
    )

    assert resolved.requires_files is True
    assert resolved.provisional is False
    assert "Provisional Resolution" not in resolved.to_prompt()


def test_task_does_not_guess_when_alias_is_absent(
    ai_dir, config, sample_skill_file
):
    resolved = resolve_context(
        config, ai_dir.parent, task="Improve the reliability of this module"
    )

    assert resolved.skill is None


def test_unknown_explicit_item_fails(ai_dir, config):
    with pytest.raises(ValueError, match="Unknown skill"):
        resolve_context(config, ai_dir.parent, skill_id="missing")


def test_json_result_explains_selection(ai_dir, config, sample_rule_file):
    resolved = resolve_context(config, ai_dir.parent, files=["src/app.ts"])
    payload = json.loads(json.dumps(resolved.to_dict()))

    assert payload["rules"][0]["id"] == "no-console-log"
    assert "matches" in payload["rules"][0]["reason"]


def test_receipt_records_metadata_without_bodies(
    ai_dir, config, sample_rule_file
):
    resolved = resolve_context(
        config,
        ai_dir.parent,
        task="Review TypeScript changes",
        files=["src/app.ts"],
    )

    path = save_resolution_receipt(resolved, "claude", ai_dir.parent / "receipts")
    receipt = load_resolution_receipt("claude", ai_dir.parent / "receipts")

    assert path.name == "claude.json"
    assert receipt["task"] == "Review TypeScript changes"
    assert receipt["expanded_rules"] == ["no-console-log"]
    assert receipt["skill"] is None
    assert receipt["provisional"] is False
    serialized = path.read_text()
    assert "Remove all `console.log` statements" not in serialized
    assert "\"body\"" not in serialized


def test_receipt_rejects_unsafe_agent_id(ai_dir, config):
    resolved = resolve_context(config, ai_dir.parent)

    with pytest.raises(ValueError, match="Invalid agent"):
        save_resolution_receipt(
            resolved, "../outside", ai_dir.parent / "receipts"
        )

    with pytest.raises(ValueError, match="Invalid agent"):
        load_resolution_receipt(
            "../outside", ai_dir.parent / "receipts"
        )
