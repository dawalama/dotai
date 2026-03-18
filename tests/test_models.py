"""Tests for dotai.models."""

from pathlib import Path

from dotai.models import (
    GlobalConfig,
    KnowledgeNode,
    NodeType,
    ProjectConfig,
    Role,
    Rule,
    Skill,
    SkillCategory,
)


class TestRole:
    def test_to_prompt_full(self):
        role = Role(
            id="reviewer",
            name="Reviewer",
            description="Reviews code",
            persona="You are a code reviewer.",
            principles=["Check edge cases", "Read errors"],
            anti_patterns=["Rubber-stamping"],
        )
        prompt = role.to_prompt()
        assert "You are a code reviewer." in prompt
        assert "## Principles" in prompt
        assert "- Check edge cases" in prompt
        assert "## Anti-patterns (avoid these)" in prompt
        assert "- Rubber-stamping" in prompt

    def test_to_prompt_minimal(self):
        role = Role(id="r", name="R", description="D", persona="Just a persona.")
        prompt = role.to_prompt()
        assert prompt == "Just a persona."
        assert "## Principles" not in prompt


class TestRule:
    def test_to_prompt_with_globs(self):
        rule = Rule(
            id="no-console",
            name="no-console-log",
            description="No console.log",
            globs=["*.ts", "*.tsx"],
            body="Remove console.log calls.",
        )
        prompt = rule.to_prompt()
        assert "### Rule: no-console-log" in prompt
        assert "**Applies to:** *.ts, *.tsx" in prompt
        assert "Remove console.log calls." in prompt

    def test_to_prompt_without_globs(self):
        rule = Rule(id="r", name="R", description="D", body="Body.")
        prompt = rule.to_prompt()
        assert "**Applies to:**" not in prompt


class TestSkill:
    def test_to_prompt_structured(self):
        skill = Skill(
            id="test-skill",
            name="Test Skill",
            description="Run tests.",
            category=SkillCategory.VERIFICATION,
            allowed_tools=["Read", "Bash"],
            inputs=[{"name": "scope", "required": False, "description": "Dir to test"}],
            steps=["Find test runner", "Run tests", "Report results"],
            gotchas=["Flaky tests need retry"],
            examples=["Run all: /run_test"],
        )
        prompt = skill.to_prompt()
        assert "# Skill: Test Skill" in prompt
        assert "**Category:** verification" in prompt
        assert "**Allowed tools:** Read, Bash" in prompt
        assert "`scope` (optional)" in prompt
        assert "1. Find test runner" in prompt
        assert "⚠️ Flaky tests need retry" in prompt

    def test_to_prompt_with_role(self):
        role = Role(id="qa", name="QA", description="Tester", persona="You test things.")
        skill = Skill(
            id="s", name="S", description="D",
            steps=["Step 1"],
        )
        prompt = skill.to_prompt(resolved_role=role)
        assert "You test things." in prompt
        assert "---" in prompt
        assert "# Skill: S" in prompt

    def test_to_prompt_runbook(self):
        skill = Skill(
            id="s", name="S", description="D",
            raw_body="```bash\necho hello\n```",
        )
        prompt = skill.to_prompt()
        assert "```bash" in prompt

    def test_is_folder_skill(self, tmp_path):
        skill_no_dir = Skill(id="s", name="S", description="D")
        assert not skill_no_dir.is_folder_skill

        skill_with_dir = Skill(id="s", name="S", description="D", assets_dir=tmp_path)
        assert skill_with_dir.is_folder_skill

    def test_scripts_property(self, tmp_path):
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "check.sh").write_text("#!/bin/bash\necho ok")
        (scripts_dir / "rollback.py").write_text("print('ok')")

        skill = Skill(id="s", name="S", description="D", assets_dir=tmp_path)
        assert len(skill.scripts) == 2

    def test_scripts_no_dir(self):
        skill = Skill(id="s", name="S", description="D")
        assert skill.scripts == []

    def test_context_in_prompt(self):
        skill = Skill(
            id="s", name="S", description="D",
            context=["production", "sensitive"],
            steps=["Do stuff"],
        )
        prompt = skill.to_prompt()
        assert "**Active in:** production, sensitive" in prompt


class TestKnowledgeNode:
    def _make_tree(self):
        child1 = KnowledgeNode(
            id="skill-review", name="Review", node_type=NodeType.SKILL,
            tags=["quality"], summary="Code review",
        )
        child2 = KnowledgeNode(
            id="skill-test", name="Test", node_type=NodeType.SKILL,
            tags=["testing"], summary="Run tests",
        )
        root = KnowledgeNode(
            id="root", name="Root", node_type=NodeType.ROOT,
            children=[child1, child2],
        )
        return root

    def test_find_by_id(self):
        root = self._make_tree()
        assert root.find_by_id("skill-review").name == "Review"
        assert root.find_by_id("nonexistent") is None

    def test_find_by_tag(self):
        root = self._make_tree()
        results = root.find_by_tag("testing")
        assert len(results) == 1
        assert results[0].id == "skill-test"

    def test_find_by_type(self):
        root = self._make_tree()
        skills = root.find_by_type(NodeType.SKILL)
        assert len(skills) == 2

    def test_find_by_text(self):
        root = self._make_tree()
        results = root.find_by_text("review")
        assert len(results) >= 1

    def test_to_toc(self):
        root = self._make_tree()
        toc = root.to_toc()
        assert "Root" in toc
        assert "Review" in toc

    def test_to_compact_json(self):
        root = self._make_tree()
        data = root.to_compact_json()
        assert data["id"] == "root"
        assert len(data["children"]) == 2


class TestGlobalConfig:
    def test_get_project(self):
        config = GlobalConfig(projects=[
            ProjectConfig(name="myapp", path=Path("/tmp/myapp")),
        ])
        assert config.get_project("myapp").name == "myapp"
        assert config.get_project("nonexistent") is None

    def test_add_project_replaces_existing(self):
        config = GlobalConfig(projects=[
            ProjectConfig(name="myapp", path=Path("/tmp/myapp")),
        ])
        config.add_project(ProjectConfig(name="myapp", path=Path("/tmp/myapp-v2")))
        assert len(config.projects) == 1
        assert config.projects[0].path == Path("/tmp/myapp-v2")

    def test_paths(self, tmp_path):
        config = GlobalConfig(global_ai_dir=tmp_path / ".ai")
        assert config.global_rules_path == tmp_path / ".ai" / "rules"
        assert config.global_skills_path == tmp_path / ".ai" / "skills"
        assert config.global_roles_path == tmp_path / ".ai" / "roles"
