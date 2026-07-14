"""Tests for deterministic rule auditing and safe compression."""

import json

import pytest

import dotai.maintenance as maintenance
from dotai.maintenance import (
    apply_compression_plan,
    audit_rules,
    build_compression_plan,
    create_compression_backup,
    estimate_tokens,
    finalize_compression_backup,
    load_compression_proposal,
    remove_reviewed_duplicates,
    write_reviewed_rule,
)
from dotai.models import GlobalConfig, ProjectConfig


def _write_rule(path, name: str, body: str, description: str | None = None):
    path.write_text(
        "---\n"
        f"name: {name}\n"
        f"description: {description or body[:80]}\n"
        "---\n\n"
        f"{body}\n"
    )
    return path


class TestAuditRules:
    def test_reports_generic_and_preference_like_rules(self, ai_dir, config):
        _write_rule(
            ai_dir / "rules" / "clean.md",
            "Write clean code",
            "Write clean code and follow best practices in every module.",
        )
        _write_rule(
            ai_dir / "rules" / "exports.md",
            "Named exports",
            "Prefer named exports when possible for application modules.",
        )

        report = audit_rules(config)
        codes = {(finding.code, finding.rule_ids[0]) for finding in report.findings}

        assert ("generic-guidance", "write-clean-code") in codes
        assert ("likely-preference", "named-exports") in codes
        assert report.estimated_tokens > 0

    def test_does_not_mark_high_consequence_rule_as_generic(self, ai_dir, config):
        _write_rule(
            ai_dir / "rules" / "secrets.md",
            "Protect credentials",
            "Follow best practices: never log credentials, passwords, or secret tokens.",
        )

        report = audit_rules(config)

        assert not any(
            finding.code == "generic-guidance" and "protect-credentials" in finding.rule_ids
            for finding in report.findings
        )

    def test_exact_duplicates_are_high_severity(self, ai_dir, config):
        body = "Always parameterize database queries. Never concatenate user input into SQL."
        _write_rule(ai_dir / "rules" / "sql-a.md", "SQL Safety A", body)
        _write_rule(ai_dir / "rules" / "sql-b.md", "SQL Safety B", body)

        report = audit_rules(config)
        duplicate = next(f for f in report.findings if f.code == "exact-duplicate")

        assert duplicate.severity == "high"
        assert duplicate.rule_ids == ["sql-safety-a", "sql-safety-b"]

    def test_token_estimate_is_stable_and_local(self):
        assert estimate_tokens("a" * 9) == 3
        assert estimate_tokens("") == 0

    def test_large_rule_reports_share_risk_and_savings(self, ai_dir, config):
        body = (
            "Never log credentials or secret tokens.\n\n"
            "## Banned patterns\n\n"
            + "- Do not print authentication material from configuration.\n" * 45
        )
        _write_rule(ai_dir / "rules" / "credentials.md", "Credentials", body)

        report = audit_rules(config)
        metric = next(metric for metric in report.rule_metrics if metric.rule_id == "credentials")
        finding = next(f for f in report.findings if f.code == "large-rule")

        assert metric.risk == "high"
        assert metric.estimated_savings_low > 0
        assert metric.estimated_savings_high >= metric.estimated_savings_low
        assert "Banned patterns" in finding.suggestion
        assert "Preserve every prohibition" in finding.suggestion
        assert "% of total" in finding.evidence


class TestCompression:
    def test_plan_only_auto_applies_exact_duplicates(self, ai_dir, config):
        body = "Always run unit tests before pushing a change to the shared branch."
        _write_rule(ai_dir / "rules" / "test-a.md", "Test A", body)
        _write_rule(ai_dir / "rules" / "test-b.md", "Test B", body)
        _write_rule(
            ai_dir / "rules" / "style.md",
            "Style",
            "Prefer named exports when possible for application modules.",
        )

        plan = build_compression_plan(config)

        assert len(plan.automatic_actions) == 1
        assert plan.automatic_actions[0].action == "remove-exact-duplicate"
        assert any(action.action == "review-as-preference" for action in plan.actions)
        assert plan.estimated_tokens_after < plan.estimated_tokens_before
        assert not (ai_dir / "backups").exists()

    def test_large_rule_becomes_review_only_trimming_candidate(self, ai_dir, config):
        body = (
            "Always use the approved rendering workflow.\n\n"
            "## Examples\n\n"
            + "- Render the document and inspect the generated output carefully.\n" * 45
        )
        _write_rule(ai_dir / "rules" / "rendering.md", "Rendering", body)

        plan = build_compression_plan(config)
        action = next(action for action in plan.actions if action.action == "review-for-trimming")

        assert action.automatic is False
        assert action.estimated_tokens_saved_low > 0
        assert action.estimated_tokens_saved_high >= action.estimated_tokens_saved_low
        assert action.source_path.endswith("rendering.md")
        assert len(action.original_sha256) == 64

    def test_loads_valid_versioned_agent_proposal(self, ai_dir, config, tmp_path):
        path = _write_rule(
            ai_dir / "rules" / "verbose.md",
            "Verbose",
            "Always run tests. " + "Repeated explanation. " * 100,
        )
        plan = build_compression_plan(config)
        action = next(action for action in plan.actions if action.action == "review-for-trimming")
        proposed = path.read_text().replace(
            "Always run tests. " + "Repeated explanation. " * 100,
            "Always run tests before pushing.",
        )
        proposal_path = tmp_path / "proposal.json"
        proposal_path.write_text(json.dumps({
            "version": 1,
            "scope": "global",
            "changes": [{
                "rule_id": "verbose",
                "source_path": action.source_path,
                "original_sha256": action.original_sha256,
                "content": proposed,
            }],
        }))

        loaded = load_compression_proposal(proposal_path, config)

        assert loaded.version == 1
        assert loaded.changes[0].rule_id == "verbose"
        assert loaded.changes[0].content == proposed

    def test_rejects_stale_agent_proposal(self, ai_dir, config, tmp_path):
        path = _write_rule(
            ai_dir / "rules" / "stale.md",
            "Stale",
            "Always run tests. " + "Repeated explanation. " * 100,
        )
        plan = build_compression_plan(config)
        action = next(action for action in plan.actions if action.action == "review-for-trimming")
        proposal_path = tmp_path / "proposal.json"
        proposal_path.write_text(json.dumps({
            "version": 1,
            "scope": "global",
            "changes": [{
                "rule_id": "stale",
                "source_path": action.source_path,
                "original_sha256": action.original_sha256,
                "content": path.read_text(),
            }],
        }))
        path.write_text(path.read_text() + "\nChanged after planning.\n")

        with pytest.raises(ValueError, match="changed after"):
            load_compression_proposal(proposal_path, config)

    def test_apply_creates_backup_before_removing_duplicate(self, ai_dir, config):
        body = "Always validate untrusted input at the system boundary before using it."
        first = _write_rule(ai_dir / "rules" / "input-a.md", "Input A", body)
        second = _write_rule(ai_dir / "rules" / "input-b.md", "Input B", body)
        original_first = first.read_text()
        original_second = second.read_text()
        plan = build_compression_plan(config)

        result = apply_compression_plan(config, plan)

        assert result.backup_path is not None
        assert first.exists()
        assert not second.exists()
        assert (result.backup_path / "rules" / first.name).read_text() == original_first
        assert (result.backup_path / "rules" / second.name).read_text() == original_second
        manifest = json.loads((result.backup_path / "manifest.json").read_text())
        assert manifest["reason"] == "compress"
        assert manifest["scope"] == "global"
        assert manifest["status"] == "complete"
        assert manifest["actual_tokens_saved"] > 0
        assert manifest["planned_removals"] == [f"rules/{second.name}"]

    def test_project_compression_does_not_touch_global_rules(self, ai_dir, tmp_path):
        body = "Always run the formatter before committing generated source files."
        global_a = _write_rule(ai_dir / "rules" / "global-a.md", "Global A", body)
        global_b = _write_rule(ai_dir / "rules" / "global-b.md", "Global B", body)
        project_path = tmp_path / "app"
        project_rules = project_path / ".ai" / "rules"
        project_rules.mkdir(parents=True)
        _write_rule(project_rules / "local.md", "Local", "Use the app-specific build command.")
        config = GlobalConfig(
            global_ai_dir=ai_dir,
            projects=[ProjectConfig(name="app", path=project_path)],
        )

        plan = build_compression_plan(config, project_name="app")
        result = apply_compression_plan(config, plan, project_name="app")

        assert result.backup_path is None
        assert plan.actions == []
        assert global_a.exists()
        assert global_b.exists()

    def test_near_duplicate_is_never_an_automatic_action(self, ai_dir, config):
        _write_rule(
            ai_dir / "rules" / "one.md",
            "One",
            "Always validate user input before constructing a database query.",
        )
        _write_rule(
            ai_dir / "rules" / "two.md",
            "Two",
            "Always validate user input before constructing a database query!",
        )

        plan = build_compression_plan(config)

        assert plan.automatic_actions == []

    def test_backup_failure_preserves_all_source_rules(self, ai_dir, config, monkeypatch):
        body = "Never expose authentication credentials in logs or error messages."
        first = _write_rule(ai_dir / "rules" / "auth-a.md", "Auth A", body)
        second = _write_rule(ai_dir / "rules" / "auth-b.md", "Auth B", body)
        plan = build_compression_plan(config)

        def fail_backup(*args, **kwargs):
            raise OSError("disk full")

        monkeypatch.setattr(maintenance, "_create_backup", fail_backup)

        with pytest.raises(OSError, match="disk full"):
            apply_compression_plan(config, plan)
        assert first.exists()
        assert second.exists()

    def test_reviewed_edit_requires_backup_and_preserves_original_snapshot(self, ai_dir, config):
        path = _write_rule(
            ai_dir / "rules" / "verbose.md",
            "Verbose",
            "Always run the formatter. " + "This explanation is repeated. " * 90,
        )
        original = path.read_text()
        plan = build_compression_plan(config)
        backup = create_compression_backup(config, plan)
        proposal = original.replace(
            "Always run the formatter. " + "This explanation is repeated. " * 90,
            "Always run the formatter before committing.",
        )

        write_reviewed_rule(
            config,
            project_name=None,
            rule_path=path,
            content=proposal,
            backup_path=backup,
        )
        manifest = finalize_compression_backup(config, backup)

        assert path.read_text() == proposal
        assert (backup / "rules" / path.name).read_text() == original
        assert manifest["status"] == "complete"
        assert manifest["changes"][0]["rule_id"] == "verbose"
        assert manifest["actual_tokens_saved"] > 0

        report = audit_rules(config)
        metric = next(metric for metric in report.rule_metrics if metric.rule_id == "verbose")
        assert metric.recent_saved_tokens == manifest["changes"][0]["saved_tokens"]

    def test_reviewed_edit_cannot_rename_rule(self, ai_dir, config):
        path = _write_rule(ai_dir / "rules" / "stable.md", "Stable", "Always keep this rule stable.")
        plan = build_compression_plan(config)
        backup = create_compression_backup(config, plan)
        renamed = path.read_text().replace("name: Stable", "name: Different")

        with pytest.raises(ValueError, match="identity"):
            write_reviewed_rule(
                config,
                project_name=None,
                rule_path=path,
                content=renamed,
                backup_path=backup,
            )
        assert "name: Stable" in path.read_text()

    def test_reviewed_edit_rechecks_source_hash_before_write(self, ai_dir, config):
        path = _write_rule(ai_dir / "rules" / "race.md", "Race", "Always preserve concurrent edits.")
        plan = build_compression_plan(config)
        backup = create_compression_backup(config, plan)
        expected_hash = maintenance._file_sha256(path)
        path.write_text(path.read_text() + "\nNewer developer change.\n")

        with pytest.raises(ValueError, match="changed after approval"):
            write_reviewed_rule(
                config,
                project_name=None,
                rule_path=path,
                content=path.read_text().replace("Newer developer change.", "Compressed."),
                backup_path=backup,
                expected_sha256=expected_hash,
            )
        assert "Newer developer change" in path.read_text()

    def test_reviewed_duplicate_removal_requires_session_backup(self, ai_dir, config):
        body = "Always use parameterized queries for untrusted database input."
        first = _write_rule(ai_dir / "rules" / "query-a.md", "Query A", body)
        second = _write_rule(ai_dir / "rules" / "query-b.md", "Query B", body)
        plan = build_compression_plan(config)
        backup = create_compression_backup(config, plan)

        removed = remove_reviewed_duplicates(
            config,
            project_name=None,
            paths=[second],
            backup_path=backup,
        )

        assert removed == [second.resolve()]
        assert first.exists()
        assert not second.exists()
        assert (backup / "rules" / second.name).exists()

    def test_apply_rejects_scope_mismatch(self, ai_dir, config):
        plan = build_compression_plan(config)
        plan.scope = "another-project"

        try:
            apply_compression_plan(config, plan)
        except ValueError as error:
            assert "scope" in str(error).lower()
        else:
            raise AssertionError("Expected a scope mismatch error")
