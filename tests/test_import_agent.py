"""Tests for agent-file migration into ~/.ai/ knowledge."""

from pathlib import Path

from dotai.import_agent import (
    apply_import_plan,
    plan_import,
    split_markdown_sections,
    strip_dotai_managed,
)
from dotai.rules import (
    build_rule_from_directive,
    build_rule_from_learning,
    check_rule_quality,
    create_rule_from_directive,
    create_rule_from_learning,
    find_duplicate_rules,
    load_rules_md,
    parse_rule_file,
)
from dotai.models import GlobalConfig
from dotai.sync import generate_primer


class TestStripDotaiManaged:
    def test_removes_markers(self):
        content = "User notes\n\n<!-- dotai:start -->\nGenerated\n<!-- dotai:end -->\n\nMore notes"
        assert "Generated" not in strip_dotai_managed(content)
        assert "User notes" in strip_dotai_managed(content)
        assert "More notes" in strip_dotai_managed(content)

    def test_no_markers(self):
        assert strip_dotai_managed("# Hello\n\nWorld") == "# Hello\n\nWorld"


class TestSplitSections:
    def test_splits_on_h2(self):
        md = "# Title\n\nIntro\n\n## One\n\nBody one\n\n## Two\n\nBody two long enough"
        sections = split_markdown_sections(md)
        titles = [t for t, _ in sections]
        assert "_preamble_" in titles
        assert "One" in titles
        assert "Two" in titles


class TestPlanImport:
    def test_directory_rules_md_combines_all_agent_files(self, tmp_path):
        (tmp_path / "CLAUDE.md").write_text("Always use pnpm for package commands.\n")
        (tmp_path / "AGENTS.md").write_text("Always run tests before pushing changes.\n")
        dest = tmp_path / ".ai"
        dest.mkdir()

        plan = plan_import(tmp_path, dest, mode="rules_md")
        assert len(plan.targets) == 1
        _, content = plan.targets[0]
        assert "Always use pnpm" in content
        assert "Always run tests" in content

    def test_rules_md_mode(self, tmp_path):
        source = tmp_path / "CLAUDE.md"
        source.write_text("# My Project\n\nAlways use pnpm.\nNever commit secrets.\n")
        dest = tmp_path / ".ai"
        dest.mkdir()
        (dest / "rules.md").write_text("# Rules\n")

        plan = plan_import(source, dest, mode="rules_md")
        assert len(plan.targets) == 1
        path, content = plan.targets[0]
        assert path.name == "rules.md"
        assert "pnpm" in content
        assert "Imported from CLAUDE.md" in content

    def test_rule_mode(self, tmp_path):
        source = tmp_path / "AGENTS.md"
        source.write_text("## Style\n\nUse tabs. Prefer explicit types everywhere.\n")
        dest = tmp_path / ".ai"
        dest.mkdir()
        (dest / "rules").mkdir()

        plan = plan_import(source, dest, mode="rule", rule_name="project-style")
        assert len(plan.targets) == 1
        path, content = plan.targets[0]
        assert path.name == "project-style.md"
        assert "name: project-style" in content
        assert "Use tabs" in content

    def test_skips_dotai_only_file(self, tmp_path):
        source = tmp_path / "AGENTS.md"
        source.write_text(
            "<!-- dotai:start -->\n# AI Knowledge Base (~/.ai/)\n\n"
            "This project uses a structured knowledge system\n<!-- dotai:end -->\n"
        )
        dest = tmp_path / ".ai"
        dest.mkdir()
        plan = plan_import(source, dest, mode="rules_md")
        assert plan.targets == []
        assert plan.warnings

    def test_apply_writes(self, tmp_path):
        source = tmp_path / "notes.md"
        source.write_text("## Conventions\n\nAlways run tests before push.\n")
        dest = tmp_path / ".ai"
        dest.mkdir()
        (dest / "rules").mkdir()
        plan = plan_import(source, dest, mode="rule", rule_name="test-before-push")
        written = apply_import_plan(plan)
        assert written[0].exists()
        assert "tests before push" in written[0].read_text().lower() or "test" in written[0].read_text().lower()

    def test_rule_mode_does_not_overwrite_existing_rule(self, tmp_path):
        source = tmp_path / "AGENTS.md"
        source.write_text("## Style\n\nPrefer explicit types everywhere.\n")
        rules_dir = tmp_path / ".ai" / "rules"
        rules_dir.mkdir(parents=True)
        existing = rules_dir / "project-style.md"
        existing.write_text("keep me")

        plan = plan_import(
            source,
            tmp_path / ".ai",
            mode="rule",
            rule_name="project-style",
        )

        assert plan.targets[0][0].name == "project-style-2.md"
        apply_import_plan(plan)
        assert existing.read_text() == "keep me"


class TestLearnStructured:
    def test_create_rule_from_directive(self, ai_dir):
        path = create_rule_from_directive(
            name="no-useeffect",
            dest_dir=ai_dir / "rules",
            directive="Never call useEffect directly; prefer declarative alternatives.",
            globs=["*.tsx", "*.ts"],
            tags=["react", "taste"],
        )
        rule = parse_rule_file(path)
        assert rule is not None
        assert rule.id == "no-useeffect"
        assert "**Directive:** Never call useEffect directly" in rule.body
        assert "**Issue:**" not in rule.body
        assert rule.globs == ["*.tsx", "*.ts"]

    def test_build_directive_does_not_write(self, ai_dir):
        dest, content = build_rule_from_directive(
            name="small-modules",
            dest_dir=ai_dir / "rules",
            directive="Prefer small, cohesive modules.",
        )
        assert "**Directive:** Prefer small, cohesive modules." in content
        assert not dest.exists()

    def test_create_rule_from_learning(self, ai_dir):
        path = create_rule_from_learning(
            name="auth-header",
            dest_dir=ai_dir / "rules",
            issue="Forgot Bearer prefix",
            correction="Always prepend Bearer to auth tokens",
            globs=["*.ts"],
            tags=["security"],
        )
        assert path.exists()
        rule = parse_rule_file(path)
        assert rule is not None
        assert rule.id == "auth-header"
        assert "Bearer" in rule.body
        assert rule.globs == ["*.ts"]

    def test_build_does_not_write(self, ai_dir):
        dest, content = build_rule_from_learning(
            name="dry-rule",
            dest_dir=ai_dir / "rules",
            issue="x",
            correction="y always do y",
        )
        assert "y always do y" in content
        assert not dest.exists()

    def test_find_duplicates(self, ai_dir, config, sample_rule_file):
        dups = find_duplicate_rules(config, "no-console-log", "Never leave console.log")
        assert any(d.id == "no-console-log" for d in dups)

    def test_check_rule_quality(self, ai_dir, config):
        (ai_dir / "rules" / "empty.md").write_text("---\nname: Empty\n---\n\nHi\n")
        findings = check_rule_quality(config)
        assert any(f["rule_id"] == "empty" for f in findings)

    def test_load_rules_md(self, ai_dir):
        text = load_rules_md(ai_dir)
        assert "clear code" in text.lower() or "Rules" in text


class TestPrimerEvolutions:
    def test_includes_freeform_rules_md(self, ai_dir, config):
        primer = generate_primer(config)
        assert "Freeform Conventions" in primer or "rules.md" in primer
        assert "clear code" in primer.lower() or "Write clear" in primer

    def test_default_omits_skill_definitions(self, ai_dir, config, sample_skill_file):
        primer = generate_primer(config)
        assert "Test Skill" in primer
        assert "## Skill Definitions" not in primer

    def test_full_includes_skill_definitions(self, ai_dir, config, sample_skill_file):
        primer = generate_primer(config, full=True)
        assert "## Skill Definitions" in primer
        assert "Run the project test suite" in primer

    def test_includes_structured_rules(self, ai_dir, config, sample_rule_file):
        primer = generate_primer(config)
        assert "no-console-log" in primer
        assert "console.log" in primer
