"""Tests for deterministic, on-demand context resolution."""

import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from dotai.context import (
    load_resolution_receipt,
    resolve_context,
    save_resolution_receipt,
)
from dotai.models import GlobalConfig, ProjectConfig
from dotai.preferences import create_preference_pack, save_active_pack_ids


def test_universal_rules_deliver_full_directives(ai_dir, config):
    (ai_dir / "rules" / "safety.md").write_text(
        "---\nname: Safety\ndescription: Never expose secrets\nglobs: *\ntags: security\n---\n"
        "FULL SECRET HANDLING PROCEDURE\n"
    )

    resolved = resolve_context(config, ai_dir.parent)

    assert [rule.id for rule in resolved.rule_summaries] == ["safety"]
    assert [rule.id for rule in resolved.rules] == ["safety"]
    prompt = resolved.to_prompt()
    assert "Never expose secrets" in prompt
    assert prompt.count("FULL SECRET HANDLING PROCEDURE") == 1
    assert resolved.reason_for("rule", "safety") == "universal rule applies to every task"


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
    history_files = list((ai_dir.parent / "receipts" / "history" / "claude").glob("*.json"))
    assert len(history_files) == 1
    assert "Remove all `console.log` statements" not in history_files[0].read_text()
    assert "\"body\"" not in history_files[0].read_text()


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


def test_freeform_notes_are_delivered_and_receipts_keep_only_sources(ai_dir, config, tmp_path):
    repo = tmp_path / "repo"
    (repo / ".ai").mkdir(parents=True)
    (repo / ".ai/rules.md").write_text("PROJECT NOTE SENTINEL")
    (ai_dir / "rules.md").write_text("GLOBAL NOTE SENTINEL")

    resolved = resolve_context(config, repo)
    assert [note.body for note in resolved.notes] == ["GLOBAL NOTE SENTINEL", "PROJECT NOTE SENTINEL"]
    assert resolved.to_prompt().count("PROJECT NOTE SENTINEL") == 1
    assert resolved.to_dict()["notes"][1]["source"] == str(repo / ".ai/rules.md")
    receipt_path = save_resolution_receipt(resolved, "claude", tmp_path / "receipts")
    receipt = json.loads(receipt_path.read_text())
    assert len(receipt["notes"]) == 2
    assert all(s["source"] for s in receipt["selections"] if s["kind"] == "note")
    for path in (tmp_path / "receipts").rglob("*.json"):
        assert "NOTE SENTINEL" not in path.read_text()


def test_general_preferences_default_and_domain_discovery(ai_dir, config):
    create_preference_pack(ai_dir / "preferences", "General", pack_id="general", body="GENERAL BODY")
    create_preference_pack(ai_dir / "preferences", "CLI", pack_id="cli", domain="cli", body="CLI BODY")
    create_preference_pack(ai_dir / "preferences", "Inactive", pack_id="inactive", domain="other", body="INACTIVE BODY")
    save_active_pack_ids(ai_dir, ["general", "cli"])

    resolved = resolve_context(config, ai_dir.parent)
    assert [p.id for p in resolved.preferences] == ["general"]
    assert [p.id for p in resolved.available_preferences] == ["cli"]
    assert "GENERAL BODY" in resolved.to_prompt()
    assert "CLI BODY" not in resolved.to_prompt()
    assert "INACTIVE BODY" not in resolved.to_prompt()
    assert resolved.to_dict()["available_preferences"][0]["domain"] == "cli"
    explicit = resolve_context(config, ai_dir.parent, extra_prefs=["cli"])
    assert {p.id for p in explicit.preferences} == {"general", "cli"}


def test_unrouted_task_is_provisional_when_file_scoped_rules_exist(ai_dir, config, sample_rule_file):
    resolved = resolve_context(config, ai_dir.parent, task="Fix the API handler")
    assert resolved.skill is None
    assert resolved.provisional
    assert resolved.to_dict()["file_scope"] == "unknown"
    with_files = resolve_context(config, ai_dir.parent, files=["src/app.ts"])
    assert not with_files.provisional
    assert with_files.to_dict()["file_scope"] == "provided"


def test_hidden_file_globs_survive_path_normalization(ai_dir, config):
    (ai_dir / "rules/env.md").write_text(
        "---\nname: Env\nglobs: .env*\n---\nNever expose environment secrets.\n"
    )
    resolved = resolve_context(config, ai_dir.parent, files=["./.env.local"])
    assert [r.id for r in resolved.rules] == ["env"]


def test_concurrent_receipts_do_not_share_temporary_files(ai_dir, config, tmp_path):
    resolved = resolve_context(config, ai_dir.parent)
    receipts = tmp_path / "receipts"
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: save_resolution_receipt(resolved, "claude", receipts), range(24)))
    assert len(list((receipts / "history/claude").glob("*.json"))) == 24
    assert load_resolution_receipt("claude", receipts) is not None
    assert list(receipts.rglob("*.tmp")) == []


def test_concurrent_receipts_tolerate_pruning_at_retention_limit(ai_dir, config, tmp_path):
    resolved = resolve_context(config, ai_dir.parent)
    receipts = tmp_path / "receipts"
    history = receipts / "history/claude"
    history.mkdir(parents=True)
    ignored_directory = history / "not-an-event.json"
    ignored_directory.mkdir()
    for n in range(500):
        (history / f"old-{n}.json").write_text('{"agent": "claude"}')

    with ThreadPoolExecutor(max_workers=12) as pool:
        list(pool.map(lambda _: save_resolution_receipt(resolved, "claude", receipts), range(30)))

    assert 0 < sum(path.is_file() for path in history.glob("*.json")) <= 500
    assert ignored_directory.is_dir()
    assert load_resolution_receipt("claude", receipts)["agent"] == "claude"
    assert list(receipts.rglob("*.tmp")) == []
