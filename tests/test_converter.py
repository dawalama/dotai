"""Tests for the Claude-native to dotai skill converter."""

import pytest
from pathlib import Path

from dotai.converter import (
    detect_skill_format,
    parse_claude_skill_md,
    _detect_structure_in_body,
    _infer_category,
    convert_claude_to_dotai,
    convert_skill_file,
)
from dotai.models import SkillCategory


# --- Fixtures ---

@pytest.fixture
def claude_skill_file(tmp_path):
    """A Claude-native SKILL.md file."""
    content = """\
---
name: PDF Summarizer
description: Summarize PDF documents using Claude
version: 1.0.0
compatibility: claude-3, claude-4
license: MIT
---

Summarize a PDF document into key takeaways.

## Parameters

- `file_path` (required): Path to the PDF file
- `length` (optional): Summary length (short, medium, long)

## Usage

- Summarize a paper: `pdf-summarizer /path/to/paper.pdf`
- Short summary: `pdf-summarizer paper.pdf --length short`

## Caveats

- Large PDFs (>100 pages) may hit token limits
- Scanned PDFs without OCR will fail silently
"""
    path = tmp_path / "SKILL.md"
    path.write_text(content)
    return path


@pytest.fixture
def claude_skill_dir(tmp_path):
    """A Claude-native skill directory with SKILL.md and scripts/."""
    skill_dir = tmp_path / "pdf-summarizer"
    skill_dir.mkdir()

    (skill_dir / "SKILL.md").write_text("""\
---
name: PDF Summarizer
description: Summarize PDFs
compatibility: claude-3
---

Summarize PDF documents.

## Steps

1. Read the PDF file
2. Extract text content
3. Generate summary

## Usage

- Basic: `summarize doc.pdf`
""")

    scripts_dir = skill_dir / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "extract.sh").write_text("#!/bin/bash\necho 'extracting'\n")

    return skill_dir


@pytest.fixture
def dotai_skill_file(tmp_path):
    """A dotai-format skill file."""
    content = """\
---
name: Code Review
trigger: /run_review
role: reviewer
category: code-quality
allowed-tools: Read, Grep, Glob
---

Review code for structural issues.

## Steps

1. Read the diff
2. Check for issues
"""
    path = tmp_path / "review.md"
    path.write_text(content)
    return path


@pytest.fixture
def unknown_md_file(tmp_path):
    """A plain markdown file with no skill markers."""
    content = "# Just a README\n\nNothing special here.\n"
    path = tmp_path / "README.md"
    path.write_text(content)
    return path


@pytest.fixture
def freeform_claude_skill(tmp_path):
    """A Claude-native skill with no structured sections."""
    content = """\
---
name: Quick Fix
compatibility: claude-4
---

Apply a quick fix to the code. Just read the error and fix it.
Be careful with imports and make sure tests still pass.

Try running the tests after applying the fix.
"""
    path = tmp_path / "SKILL.md"
    path.write_text(content)
    return path


# --- detect_skill_format ---

class TestDetectSkillFormat:
    def test_detects_dotai_by_frontmatter(self, dotai_skill_file):
        assert detect_skill_format(dotai_skill_file) == "dotai"

    def test_detects_claude_native_by_frontmatter(self, claude_skill_file):
        assert detect_skill_format(claude_skill_file) == "claude-native"

    def test_detects_claude_native_by_filename(self, tmp_path):
        skill = tmp_path / "SKILL.md"
        skill.write_text("# A skill\n\nDo something.\n")
        assert detect_skill_format(skill) == "claude-native"

    def test_detects_claude_native_directory(self, claude_skill_dir):
        assert detect_skill_format(claude_skill_dir) == "claude-native"

    def test_detects_dotai_directory(self, tmp_path):
        skill_dir = tmp_path / "myskill"
        skill_dir.mkdir()
        (skill_dir / "main.md").write_text("---\ntrigger: /run_x\n---\n\nDo stuff.\n")
        assert detect_skill_format(skill_dir) == "dotai"

    def test_detects_unknown(self, unknown_md_file):
        assert detect_skill_format(unknown_md_file) == "unknown"

    def test_nonexistent_file(self, tmp_path):
        assert detect_skill_format(tmp_path / "nope.md") == "unknown"

    def test_detects_dotai_by_body_sections(self, tmp_path):
        content = "---\nname: Test\n---\n\nDesc.\n\n## Steps\n\n1. Do thing\n"
        path = tmp_path / "test.md"
        path.write_text(content)
        assert detect_skill_format(path) == "dotai"

    def test_detects_claude_native_by_scripts_sibling(self, tmp_path):
        (tmp_path / "scripts").mkdir()
        skill = tmp_path / "skill.md"
        skill.write_text("---\nname: Test\n---\n\nDo stuff.\n")
        assert detect_skill_format(skill) == "claude-native"


# --- parse_claude_skill_md ---

class TestParseClaudeSkillMd:
    def test_parses_frontmatter(self, claude_skill_file):
        result = parse_claude_skill_md(claude_skill_file)
        assert result["frontmatter"]["name"] == "PDF Summarizer"
        assert result["frontmatter"]["compatibility"] == "claude-3, claude-4"
        assert result["frontmatter"]["license"] == "MIT"

    def test_parses_body(self, claude_skill_file):
        result = parse_claude_skill_md(claude_skill_file)
        assert "Summarize a PDF document" in result["body"]

    def test_detects_scripts_dir(self, claude_skill_dir):
        result = parse_claude_skill_md(claude_skill_dir)
        assert result["has_scripts"] is True
        assert result["has_references"] is False

    def test_parses_from_directory(self, claude_skill_dir):
        result = parse_claude_skill_md(claude_skill_dir)
        assert result["frontmatter"]["name"] == "PDF Summarizer"


# --- _detect_structure_in_body ---

class TestDetectStructureInBody:
    def test_detects_parameters_section(self):
        body = "Desc.\n\n## Parameters\n\n- `file` (required): The file\n- `mode` (optional): Mode\n"
        result = _detect_structure_in_body(body)
        assert result["is_structured"] is True
        assert len(result["inputs"]) == 2
        assert result["inputs"][0]["name"] == "file"
        assert result["inputs"][0]["required"] is True

    def test_detects_usage_section(self):
        body = "Desc.\n\n## Usage\n\n- Run it: `cmd arg`\n- Other: `cmd --flag`\n"
        result = _detect_structure_in_body(body)
        assert result["is_structured"] is True
        assert len(result["examples"]) == 2

    def test_detects_caveats_section(self):
        body = "Desc.\n\n## Caveats\n\n- Watch out for X\n- Be careful with Y\n"
        result = _detect_structure_in_body(body)
        assert result["is_structured"] is True
        assert len(result["gotchas"]) == 2

    def test_detects_numbered_steps(self):
        body = "Desc.\n\n## Steps\n\n1. First step\n2. Second step\n3. Third step\n"
        result = _detect_structure_in_body(body)
        assert result["is_structured"] is True
        assert len(result["steps"]) == 3

    def test_extracts_description(self):
        body = "This is the description.\n\n## Parameters\n\n- `x`: thing\n"
        result = _detect_structure_in_body(body)
        assert result["description"] == "This is the description."

    def test_freeform_body(self):
        body = "Just do the thing.\nBe careful.\n"
        result = _detect_structure_in_body(body)
        assert result["is_structured"] is False
        assert result["description"] == "Just do the thing.\nBe careful."

    def test_numbered_list_without_section_header_is_freeform(self):
        body = "Do the following:\n\n1. Step one\n2. Step two\n"
        result = _detect_structure_in_body(body)
        # Numbered lists alone don't make it structured — needs a recognized section header
        assert result["is_structured"] is False
        assert len(result["steps"]) == 0

    def test_numbered_list_with_section_header_is_structured(self):
        body = "Desc.\n\n## Parameters\n\n- `x` (required): thing\n\n1. Step one\n2. Step two\n"
        result = _detect_structure_in_body(body)
        assert result["is_structured"] is True
        assert len(result["steps"]) == 2

    def test_alternative_section_names(self):
        body = "Desc.\n\n## Arguments\n\n- `x` (required): thing\n\n## Warnings\n\n- Don't do Y\n"
        result = _detect_structure_in_body(body)
        assert len(result["inputs"]) == 1
        assert len(result["gotchas"]) == 1


# --- _infer_category ---

class TestInferCategory:
    def test_review_maps_to_code_quality(self):
        assert _infer_category("Code Review", "Review code") == SkillCategory.CODE_QUALITY

    def test_test_maps_to_verification(self):
        assert _infer_category("Run Tests", "Execute test suite") == SkillCategory.VERIFICATION

    def test_deploy_maps_to_deployment(self):
        assert _infer_category("Deploy", "Deploy to production") == SkillCategory.DEPLOYMENT

    def test_debug_maps_to_debugging(self):
        assert _infer_category("Debugger", "Debug issues") == SkillCategory.DEBUGGING

    def test_scaffold_maps_to_scaffolding(self):
        assert _infer_category("Scaffold", "Generate boilerplate") == SkillCategory.SCAFFOLDING

    def test_mvp_maps_to_scaffolding(self):
        assert _infer_category("mvp", "Build minimum viable product") == SkillCategory.SCAFFOLDING

    def test_pricing_maps_to_workflow(self):
        assert _infer_category("pricing", "Set pricing strategy") == SkillCategory.WORKFLOW

    def test_marketing_maps_to_workflow(self):
        assert _infer_category("marketing-plan", "Create a marketing plan") == SkillCategory.WORKFLOW

    def test_unknown_defaults_to_workflow(self):
        assert _infer_category("foo bar", "something random") == SkillCategory.WORKFLOW

    def test_infers_from_description_when_name_is_generic(self):
        assert _infer_category("my-thing", "lint code for issues") == SkillCategory.CODE_QUALITY

    def test_migrate_maps_to_maintenance(self):
        assert _infer_category("migrate-db", "Run database migrations") == SkillCategory.MAINTENANCE

    def test_monitor_maps_to_data(self):
        assert _infer_category("monitor", "Watch dashboard metrics") == SkillCategory.DATA


# --- convert_claude_to_dotai ---

class TestConvertClaudeToDotai:
    def test_converts_structured_skill(self, claude_skill_file, tmp_path):
        dest = tmp_path / "output"
        result = convert_claude_to_dotai(claude_skill_file, dest)

        assert result.exists()
        content = result.read_text()
        assert "name: PDF Summarizer" in content
        assert "## Inputs" in content
        assert "## Examples" in content
        assert "## Gotchas" in content
        assert "`file_path`" in content

    def test_sets_trigger(self, claude_skill_file, tmp_path):
        dest = tmp_path / "output"
        result = convert_claude_to_dotai(claude_skill_file, dest)
        content = result.read_text()
        assert "trigger: /run_pdf-summarizer" in content

    def test_infers_category(self, claude_skill_file, tmp_path):
        dest = tmp_path / "output"
        result = convert_claude_to_dotai(claude_skill_file, dest)
        content = result.read_text()
        # Should have a real category line (not commented)
        assert "\ncategory: " in content
        # Should not be commented out
        assert "# category:" not in content

    def test_preserves_tags_from_compatibility(self, claude_skill_file, tmp_path):
        dest = tmp_path / "output"
        result = convert_claude_to_dotai(claude_skill_file, dest)
        content = result.read_text()
        assert "claude-3" in content
        assert "claude-4" in content

    def test_comments_license(self, claude_skill_file, tmp_path):
        dest = tmp_path / "output"
        result = convert_claude_to_dotai(claude_skill_file, dest)
        content = result.read_text()
        assert "# license: MIT" in content

    def test_creates_folder_skill_with_scripts(self, claude_skill_dir, tmp_path):
        dest = tmp_path / "output"
        result = convert_claude_to_dotai(claude_skill_dir, dest)

        assert result.is_dir()
        assert (result / "main.md").exists()
        assert (result / "scripts").is_dir()
        assert (result / "scripts" / "extract.sh").exists()

    def test_freeform_becomes_runbook(self, freeform_claude_skill, tmp_path):
        dest = tmp_path / "output"
        result = convert_claude_to_dotai(freeform_claude_skill, dest)
        content = result.read_text()
        # Freeform content should be preserved
        assert "quick fix" in content.lower() or "Quick Fix" in content

    def test_custom_skill_name(self, claude_skill_file, tmp_path):
        dest = tmp_path / "output"
        result = convert_claude_to_dotai(claude_skill_file, dest, skill_name="my-summarizer")
        content = result.read_text()
        assert "name: my-summarizer" in content

    def test_idempotent_dest_dir(self, claude_skill_file, tmp_path):
        dest = tmp_path / "output"
        # Convert twice — should not error
        convert_claude_to_dotai(claude_skill_file, dest)
        result = convert_claude_to_dotai(claude_skill_file, dest)
        assert result.exists()


# --- convert_skill_file ---

class TestConvertSkillFile:
    def test_converts_claude_native(self, claude_skill_file, tmp_path):
        dest = tmp_path / "output"
        result = convert_skill_file(claude_skill_file, dest)
        assert result.exists()
        content = result.read_text()
        assert "name:" in content

    def test_copies_dotai_unchanged(self, dotai_skill_file, tmp_path):
        dest = tmp_path / "output"
        result = convert_skill_file(dotai_skill_file, dest)
        assert result.exists()
        original = dotai_skill_file.read_text()
        assert result.read_text() == original

    def test_copies_unknown_unchanged(self, unknown_md_file, tmp_path):
        dest = tmp_path / "output"
        result = convert_skill_file(unknown_md_file, dest)
        assert result.exists()
        assert result.read_text() == unknown_md_file.read_text()

    def test_copies_directory(self, tmp_path):
        src = tmp_path / "src_skill"
        src.mkdir()
        (src / "main.md").write_text("---\ntrigger: /run_x\n---\n\nStuff\n")
        (src / "config.json").write_text("{}")

        dest = tmp_path / "output"
        result = convert_skill_file(src, dest)
        assert result.is_dir()
        assert (result / "main.md").exists()
        assert (result / "config.json").exists()
