"""Tests for the multi-ecosystem skill converter."""

import json
import pytest
from pathlib import Path

from dotai.converter import (
    detect_skill_format,
    parse_claude_skill_md,
    parse_plugin_manifest,
    convert_plugin_to_dotai,
    _detect_structure_in_body,
    _infer_category,
    _convert_gemini_command,
    _convert_agent_to_role,
    _convert_cursor_rule,
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


# --- Plugin / Extension Fixtures ---

@pytest.fixture
def claude_plugin(tmp_path):
    """A Claude Code plugin directory."""
    plugin = tmp_path / "my-claude-plugin"
    plugin.mkdir()

    # Manifest
    cp_dir = plugin / ".claude-plugin"
    cp_dir.mkdir()
    (cp_dir / "plugin.json").write_text(json.dumps({
        "name": "code-review",
        "description": "Code review tools",
        "author": {"name": "Test Author", "email": "test@example.com"},
    }))

    # A skill
    skill_dir = plugin / "skills" / "review-code"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("""\
---
name: review-code
description: Review code for structural issues
allowed-tools: [Read, Glob, Grep, Bash]
---

# Code Reviewer

## Workflow
1. Read the diff
2. Identify issues
3. Report findings
""")

    # A command (legacy)
    cmd_dir = plugin / "commands"
    cmd_dir.mkdir()
    (cmd_dir / "quick-fix.md").write_text("""\
---
description: Apply a quick fix
allowed-tools: [Read, Edit]
---

Fix the issue described by the user. Read the error, find the cause, apply the fix.
""")

    # An agent
    agents_dir = plugin / "agents"
    agents_dir.mkdir()
    (agents_dir / "researcher.md").write_text("""\
---
name: researcher
description: Research agent for gathering context
tools: Glob, Grep, Read, WebFetch
model: sonnet
---

You are a research agent. Your job is to gather context and information.
Search broadly, read carefully, and summarize findings.
""")

    # Hooks (non-convertible)
    hooks_dir = plugin / "hooks"
    hooks_dir.mkdir()
    (hooks_dir / "hooks.json").write_text("{}")

    return plugin


@pytest.fixture
def cursor_plugin(tmp_path):
    """A Cursor plugin directory."""
    plugin = tmp_path / "my-cursor-plugin"
    plugin.mkdir()

    # Manifest
    cp_dir = plugin / ".cursor-plugin"
    cp_dir.mkdir()
    (cp_dir / "plugin.json").write_text(json.dumps({
        "name": "typescript-tools",
        "description": "TypeScript development tools",
        "version": "1.0.0",
        "author": {"name": "Cursor Dev"},
    }))

    # A skill
    skill_dir = plugin / "skills" / "ts-migrate"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("""\
---
name: ts-migrate
description: Migrate JavaScript files to TypeScript
---

# TypeScript Migration

## Steps
1. Find .js files
2. Rename to .ts/.tsx
3. Add type annotations
4. Fix type errors
""")

    # A .mdc rule
    rules_dir = plugin / "rules"
    rules_dir.mkdir()
    (rules_dir / "typescript-strict.mdc").write_text("""\
---
description: Enforce strict TypeScript conventions
globs: **/*.ts,**/*.tsx
alwaysApply: false
---

# TypeScript Strict Mode

- Always use explicit return types on exported functions
- Prefer `interface` over `type` for object shapes
- Never use `any` — use `unknown` instead
""")

    return plugin


@pytest.fixture
def gemini_extension(tmp_path):
    """A Gemini CLI extension directory."""
    ext = tmp_path / "my-gemini-ext"
    ext.mkdir()

    # Manifest
    (ext / "gemini-extension.json").write_text(json.dumps({
        "name": "git-helper",
        "version": "1.0.0",
        "description": "Git workflow helpers",
        "mcpServers": {
            "git-server": {
                "command": "node",
                "args": ["server.js"],
            }
        },
    }))

    # A skill
    skill_dir = ext / "skills" / "commit-helper"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("""\
---
name: commit-helper
description: Generate conventional commit messages from staged changes
---

# Commit Helper

Review staged changes and generate a conventional commit message.

## Steps
1. Run git diff --cached
2. Analyze the changes
3. Generate commit message
""")

    # A TOML command
    cmd_dir = ext / "commands" / "git"
    cmd_dir.mkdir(parents=True)
    (cmd_dir / "commit.toml").write_text('''\
description = "Generate a commit message from staged changes"
prompt = """
Generate a Conventional Commit message based on this diff:

```diff
!{git diff --staged}
```

Use the format: type(scope): description
"""
''')

    # Another TOML command at top level
    cmd_top = ext / "commands"
    (cmd_top / "status.toml").write_text('''\
description = "Show project status summary"
prompt = """
Summarize the current state of this project:

```
!{git status}
```

```
!{git log --oneline -5}
```
"""
''')

    return ext


# --- detect_skill_format for plugins ---

class TestDetectPluginFormat:
    def test_detects_claude_plugin(self, claude_plugin):
        assert detect_skill_format(claude_plugin) == "claude-plugin"

    def test_detects_cursor_plugin(self, cursor_plugin):
        assert detect_skill_format(cursor_plugin) == "cursor-plugin"

    def test_detects_gemini_extension(self, gemini_extension):
        assert detect_skill_format(gemini_extension) == "gemini-extension"

    def test_plugin_detection_takes_priority_over_skill(self, tmp_path):
        """A directory with both plugin.json and SKILL.md should detect as plugin."""
        plugin = tmp_path / "hybrid"
        plugin.mkdir()
        (plugin / ".claude-plugin").mkdir()
        (plugin / ".claude-plugin" / "plugin.json").write_text('{"name": "test"}')
        (plugin / "SKILL.md").write_text("---\nname: test\n---\nStuff\n")
        assert detect_skill_format(plugin) == "claude-plugin"


# --- parse_plugin_manifest ---

class TestParsePluginManifest:
    def test_parses_claude_plugin(self, claude_plugin):
        result = parse_plugin_manifest(claude_plugin)
        assert result["format"] == "claude-plugin"
        assert result["name"] == "code-review"
        assert result["description"] == "Code review tools"
        assert result["author"] == "Test Author"
        assert len(result["skills"]) == 1
        assert len(result["commands"]) == 1
        assert len(result["agents"]) == 1
        assert result["has_hooks"] is True

    def test_parses_cursor_plugin(self, cursor_plugin):
        result = parse_plugin_manifest(cursor_plugin)
        assert result["format"] == "cursor-plugin"
        assert result["name"] == "typescript-tools"
        assert len(result["skills"]) == 1
        assert len(result["rules"]) == 1

    def test_parses_gemini_extension(self, gemini_extension):
        result = parse_plugin_manifest(gemini_extension)
        assert result["format"] == "gemini-extension"
        assert result["name"] == "git-helper"
        assert len(result["skills"]) == 1
        assert len(result["commands"]) == 2
        assert result["has_mcp"] is True

    def test_unknown_dir_returns_empty(self, tmp_path):
        result = parse_plugin_manifest(tmp_path)
        assert result["format"] == "unknown"
        assert result["skills"] == []

    def test_string_author_field(self, tmp_path):
        plugin = tmp_path / "p"
        plugin.mkdir()
        (plugin / ".claude-plugin").mkdir()
        (plugin / ".claude-plugin" / "plugin.json").write_text(
            json.dumps({"name": "test", "author": "Just a string"})
        )
        result = parse_plugin_manifest(plugin)
        assert result["author"] == "Just a string"


# --- convert_plugin_to_dotai ---

class TestConvertPluginToDotai:
    def test_converts_claude_plugin_skills(self, claude_plugin, tmp_path):
        dest = tmp_path / "output"
        results = convert_plugin_to_dotai(claude_plugin, dest)
        # Should convert the skill + the command
        assert len(results) == 2
        # Check that skill was converted
        skill_files = list(dest.glob("*.md"))
        assert len(skill_files) >= 1
        # Verify content of converted skill
        contents = [f.read_text() for f in skill_files]
        all_content = "\n".join(contents)
        assert "review-code" in all_content or "review" in all_content

    def test_converts_cursor_plugin_skills(self, cursor_plugin, tmp_path):
        dest = tmp_path / "output"
        results = convert_plugin_to_dotai(cursor_plugin, dest)
        assert len(results) >= 1
        # Verify the skill was converted
        all_content = "\n".join(f.read_text() for f in results if f.exists() and f.is_file())
        assert "ts-migrate" in all_content or "migrate" in all_content

    def test_converts_gemini_extension_skills_and_commands(self, gemini_extension, tmp_path):
        dest = tmp_path / "output"
        results = convert_plugin_to_dotai(gemini_extension, dest)
        # 1 skill + 2 toml commands
        assert len(results) == 3

    def test_skill_filter(self, claude_plugin, tmp_path):
        dest = tmp_path / "output"
        results = convert_plugin_to_dotai(claude_plugin, dest, skill_filter="review-code")
        assert len(results) == 1

    def test_include_agents(self, claude_plugin, tmp_path):
        dest = tmp_path / "output" / "skills"
        dest.mkdir(parents=True)
        results = convert_plugin_to_dotai(claude_plugin, dest, include_agents=True)
        # skills (1) + commands (1) + agents (1) = 3
        assert len(results) == 3
        # Check role was created
        roles_dir = dest.parent / "roles"
        assert roles_dir.exists()
        role_files = list(roles_dir.glob("*.md"))
        assert len(role_files) == 1
        assert "researcher" in role_files[0].read_text().lower()

    def test_include_rules(self, cursor_plugin, tmp_path):
        dest = tmp_path / "output" / "skills"
        dest.mkdir(parents=True)
        results = convert_plugin_to_dotai(cursor_plugin, dest, include_rules=True)
        # 1 skill + 1 rule
        assert len(results) == 2
        rules_dir = dest.parent / "rules"
        assert rules_dir.exists()
        rule_files = list(rules_dir.glob("*.md"))
        assert len(rule_files) == 1
        content = rule_files[0].read_text()
        assert "TypeScript" in content or "typescript" in content


# --- _convert_gemini_command ---

class TestConvertGeminiCommand:
    def test_converts_toml_command(self, gemini_extension, tmp_path):
        cmd = gemini_extension / "commands" / "git" / "commit.toml"
        dest = tmp_path / "output"
        result = _convert_gemini_command(cmd, dest)
        assert result is not None
        assert result.exists()
        content = result.read_text()
        assert "trigger: /run_" in content
        assert "git diff --staged" in content
        assert "category:" in content

    def test_notes_template_variables(self, gemini_extension, tmp_path):
        cmd = gemini_extension / "commands" / "git" / "commit.toml"
        dest = tmp_path / "output"
        result = _convert_gemini_command(cmd, dest)
        content = result.read_text()
        # Should note the !{} template syntax
        assert "!{command}" in content

    def test_returns_none_for_invalid_toml(self, tmp_path):
        bad = tmp_path / "bad.toml"
        bad.write_text("this is not valid {{{ toml")
        result = _convert_gemini_command(bad, tmp_path / "out")
        assert result is None


# --- _convert_agent_to_role ---

class TestConvertAgentToRole:
    def test_converts_agent_md(self, claude_plugin, tmp_path):
        agent = claude_plugin / "agents" / "researcher.md"
        dest = tmp_path / "roles"
        result = _convert_agent_to_role(agent, dest)
        assert result is not None
        assert result.exists()
        content = result.read_text()
        assert "name: researcher" in content
        assert "research agent" in content.lower()

    def test_role_has_tags(self, claude_plugin, tmp_path):
        agent = claude_plugin / "agents" / "researcher.md"
        dest = tmp_path / "roles"
        result = _convert_agent_to_role(agent, dest)
        content = result.read_text()
        assert "imported" in content


# --- _convert_cursor_rule ---

class TestConvertCursorRule:
    def test_converts_mdc_rule(self, cursor_plugin, tmp_path):
        rule = cursor_plugin / "rules" / "typescript-strict.mdc"
        dest = tmp_path / "rules"
        result = _convert_cursor_rule(rule, dest)
        assert result is not None
        assert result.exists()
        content = result.read_text()
        assert "description:" in content
        assert "globs:" in content
        assert "**.ts" in content or "**/*.ts" in content

    def test_rule_has_cursor_tag(self, cursor_plugin, tmp_path):
        rule = cursor_plugin / "rules" / "typescript-strict.mdc"
        dest = tmp_path / "rules"
        result = _convert_cursor_rule(rule, dest)
        content = result.read_text()
        assert "cursor" in content


# --- convert_skill_file with plugins ---

class TestConvertSkillFilePlugin:
    def test_routes_claude_plugin(self, claude_plugin, tmp_path):
        dest = tmp_path / "output"
        result = convert_skill_file(claude_plugin, dest)
        assert result.exists()

    def test_routes_gemini_extension(self, gemini_extension, tmp_path):
        dest = tmp_path / "output"
        result = convert_skill_file(gemini_extension, dest)
        assert result.exists()
