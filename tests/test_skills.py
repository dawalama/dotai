"""Tests for dotai.skills parsing."""

import json

from dotai.models import SkillCategory
from dotai.skills import (
    _parse_category,
    _parse_list_field,
    load_skills_from_dir,
    parse_skill_file,
)


class TestParseListField:
    def test_comma_separated(self):
        assert _parse_list_field("Read, Grep, Bash") == ["Read", "Grep", "Bash"]

    def test_empty(self):
        assert _parse_list_field("") == []

    def test_strips_brackets(self):
        assert _parse_list_field("[Read, Grep]") == ["Read", "Grep"]


class TestParseCategory:
    def test_direct_match(self):
        assert _parse_category("workflow") == SkillCategory.WORKFLOW

    def test_alias(self):
        assert _parse_category("testing") == SkillCategory.VERIFICATION
        assert _parse_category("deploy") == SkillCategory.DEPLOYMENT
        assert _parse_category("review") == SkillCategory.CODE_QUALITY
        assert _parse_category("debug") == SkillCategory.DEBUGGING

    def test_case_insensitive(self):
        assert _parse_category("Workflow") == SkillCategory.WORKFLOW
        assert _parse_category("DEPLOY") == SkillCategory.DEPLOYMENT

    def test_unknown(self):
        assert _parse_category("bogus") is None


class TestParseSkillFile:
    def test_structured_skill(self, sample_skill_file):
        skill = parse_skill_file(sample_skill_file)
        assert skill is not None
        assert skill.name == "Test Skill"
        assert skill.trigger == "/run_test"
        assert skill.role == "test-reviewer"
        assert skill.category == SkillCategory.VERIFICATION
        assert skill.allowed_tools == ["Read", "Grep", "Bash"]
        assert "testing" in skill.tags
        assert "ci" in skill.tags
        assert "local" in skill.context
        assert "ci" in skill.context
        assert len(skill.inputs) == 2
        assert skill.inputs[0]["name"] == "scope"
        assert skill.inputs[0]["required"] is False
        assert skill.inputs[1]["name"] == "verbose"
        assert skill.inputs[1]["required"] is True
        assert len(skill.steps) == 4
        assert "Detect the test runner" in skill.steps[0]
        assert len(skill.examples) == 2
        assert len(skill.gotchas) == 2
        assert "Flaky tests" in skill.gotchas[0]

    def test_nonexistent_file(self, tmp_path):
        assert parse_skill_file(tmp_path / "nope.md") is None

    def test_runbook_skill(self, tmp_path):
        content = """\
---
name: Deploy
trigger: /run_deploy
category: deployment
---

Deploy the application to production.

```bash
kubectl apply -f deploy.yaml
kubectl rollout status deployment/app
```

## Step 1: Verify

Check that pods are healthy.
"""
        path = tmp_path / "deploy.md"
        path.write_text(content)
        skill = parse_skill_file(path)
        assert skill is not None
        assert skill.name == "Deploy"
        assert skill.raw_body  # runbook mode keeps the body
        assert "kubectl" in skill.raw_body

    def test_no_frontmatter(self, tmp_path):
        path = tmp_path / "bare.md"
        path.write_text("Just a description.\n\n## Steps\n\n1. Do something\n")
        skill = parse_skill_file(path)
        assert skill is not None
        assert skill.name == "Bare"  # derived from filename
        assert len(skill.steps) == 1

    def test_folder_skill(self, tmp_path):
        skill_dir = tmp_path / "skills" / "deploy"
        skill_dir.mkdir(parents=True)
        (skill_dir / "main.md").write_text(
            "---\nname: Deploy\ntrigger: /run_deploy\ncategory: deployment\n---\n\nDeploy app.\n\n## Steps\n\n1. Push\n"
        )
        (skill_dir / "config.json").write_text(json.dumps({"region": "us-east-1"}))
        scripts = skill_dir / "scripts"
        scripts.mkdir()
        (scripts / "health.sh").write_text("#!/bin/bash\ncurl localhost/health")

        skill = parse_skill_file(
            skill_dir / "main.md",
            assets_dir=skill_dir,
            skill_config={"region": "us-east-1"},
        )
        assert skill is not None
        assert skill.is_folder_skill
        assert skill.config["region"] == "us-east-1"
        assert len(skill.scripts) == 1


class TestLoadSkillsFromDir:
    def test_loads_single_files(self, ai_dir):
        (ai_dir / "skills" / "a.md").write_text(
            "---\nname: Alpha\n---\n\nAlpha skill.\n\n## Steps\n\n1. Go\n"
        )
        (ai_dir / "skills" / "b.md").write_text(
            "---\nname: Beta\n---\n\nBeta skill.\n\n## Steps\n\n1. Go\n"
        )
        skills = load_skills_from_dir(ai_dir / "skills")
        assert len(skills) == 2

    def test_loads_folder_skills(self, ai_dir):
        deploy = ai_dir / "skills" / "deploy"
        deploy.mkdir()
        (deploy / "main.md").write_text(
            "---\nname: Deploy\n---\n\nDeploy.\n\n## Steps\n\n1. Ship\n"
        )
        skills = load_skills_from_dir(ai_dir / "skills")
        assert len(skills) == 1
        assert skills[0].is_folder_skill

    def test_missing_dir(self, tmp_path):
        assert load_skills_from_dir(tmp_path / "nope") == []
