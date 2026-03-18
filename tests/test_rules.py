"""Tests for dotai.rules parsing."""

from pathlib import Path

from dotai.models import GlobalConfig, ProjectConfig
from dotai.rules import (
    load_rules_from_dir,
    parse_rule_file,
    resolve_rules_for_project,
    toggle_rule_global,
)


class TestParseRuleFile:
    def test_full_rule(self, sample_rule_file):
        rule = parse_rule_file(sample_rule_file)
        assert rule is not None
        assert rule.name == "no-console-log"
        assert rule.id == "no-console-log"
        assert rule.description == "Never leave console.log in production code"
        assert rule.enabled is True
        assert rule.globs == ["*.ts", "*.tsx"]
        assert "quality" in rule.tags
        assert "console.log" in rule.body

    def test_nonexistent_file(self, tmp_path):
        assert parse_rule_file(tmp_path / "nope.md") is None

    def test_disabled_rule(self, tmp_path):
        path = tmp_path / "off.md"
        path.write_text("---\nname: Off Rule\nenabled: false\n---\n\nDisabled.\n")
        rule = parse_rule_file(path)
        assert rule.enabled is False

    def test_no_frontmatter(self, tmp_path):
        path = tmp_path / "bare.md"
        path.write_text("Always use strict mode.\n")
        rule = parse_rule_file(path)
        assert rule is not None
        assert rule.name == "Bare"

    def test_auto_description(self, tmp_path):
        path = tmp_path / "auto.md"
        path.write_text("---\nname: Auto\n---\n\nUse parameterized queries for all SQL.\n")
        rule = parse_rule_file(path)
        assert "parameterized" in rule.description.lower()


class TestLoadRulesFromDir:
    def test_loads_multiple(self, ai_dir):
        (ai_dir / "rules" / "a.md").write_text("---\nname: A\n---\n\nRule A.\n")
        (ai_dir / "rules" / "b.md").write_text("---\nname: B\n---\n\nRule B.\n")
        rules = load_rules_from_dir(ai_dir / "rules")
        assert len(rules) == 2

    def test_empty_dir(self, ai_dir):
        assert load_rules_from_dir(ai_dir / "rules") == []


class TestResolveRulesForProject:
    def test_global_rules_only(self, ai_dir):
        (ai_dir / "rules" / "r1.md").write_text("---\nname: R1\n---\n\nRule.\n")
        config = GlobalConfig(global_ai_dir=ai_dir)
        rules = resolve_rules_for_project(config)
        assert len(rules) == 1

    def test_disabled_rule_excluded(self, ai_dir):
        (ai_dir / "rules" / "r1.md").write_text("---\nname: R1\nenabled: false\n---\n\nOff.\n")
        config = GlobalConfig(global_ai_dir=ai_dir)
        rules = resolve_rules_for_project(config)
        assert len(rules) == 0

    def test_project_disables_global_rule(self, ai_dir, tmp_path):
        (ai_dir / "rules" / "r1.md").write_text("---\nname: R1\n---\n\nRule.\n")
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / ".ai" / "rules").mkdir(parents=True)

        config = GlobalConfig(
            global_ai_dir=ai_dir,
            projects=[ProjectConfig(name="proj", path=proj, disabled_rules=["r1"])],
        )
        rules = resolve_rules_for_project(config, "proj")
        assert len(rules) == 0

    def test_project_rules_added(self, ai_dir, tmp_path):
        proj = tmp_path / "proj"
        proj.mkdir()
        proj_rules = proj / ".ai" / "rules"
        proj_rules.mkdir(parents=True)
        (proj_rules / "local.md").write_text("---\nname: Local\n---\n\nLocal rule.\n")

        config = GlobalConfig(
            global_ai_dir=ai_dir,
            projects=[ProjectConfig(name="proj", path=proj)],
        )
        rules = resolve_rules_for_project(config, "proj")
        assert any(r.name == "Local" for r in rules)


class TestToggleRuleGlobal:
    def test_toggle_off(self, ai_dir):
        path = ai_dir / "rules" / "r1.md"
        path.write_text("---\nname: R1\nenabled: true\n---\n\nRule.\n")
        assert toggle_rule_global("r1", ai_dir / "rules", enabled=False)
        content = path.read_text()
        assert "enabled: false" in content

    def test_toggle_nonexistent(self, ai_dir):
        assert not toggle_rule_global("nope", ai_dir / "rules", enabled=True)
