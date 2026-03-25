"""Shared test fixtures for dotai tests."""

import json
from pathlib import Path

import pytest

from dotai.models import GlobalConfig, ProjectConfig


@pytest.fixture
def ai_dir(tmp_path):
    """Create a minimal ~/.ai/ structure in a temp directory."""
    ai = tmp_path / ".ai"
    ai.mkdir()
    (ai / "roles").mkdir()
    (ai / "skills").mkdir()
    (ai / "rules").mkdir()
    (ai / "tools").mkdir()
    (ai / "rules.md").write_text("# Global Rules\n\n- Write clear code\n")
    return ai


@pytest.fixture
def config(ai_dir):
    """A GlobalConfig pointing at the temp ai_dir."""
    return GlobalConfig(global_ai_dir=ai_dir)


@pytest.fixture
def config_dir(tmp_path):
    """A temp config directory (replaces ~/.config/dotai)."""
    d = tmp_path / "config"
    d.mkdir()
    return d


@pytest.fixture
def project_dir(tmp_path):
    """A temp project directory for sync output."""
    d = tmp_path / "my-project"
    d.mkdir()
    return d


@pytest.fixture
def sample_role_file(ai_dir):
    """Write a sample role file and return its path."""
    content = """\
---
name: Test Reviewer
description: A reviewer for tests
tags: review, testing
---

You are a test reviewer who checks code for correctness.

## Principles

- Always check edge cases
- Read error messages carefully

## Anti-patterns (avoid these)

- Rubber-stamping PRs
- Ignoring test failures
"""
    path = ai_dir / "roles" / "test-reviewer.md"
    path.write_text(content)
    return path


@pytest.fixture
def sample_skill_file(ai_dir):
    """Write a sample structured skill file and return its path."""
    content = """\
---
name: Test Skill
trigger: /run_test
role: test-reviewer
category: verification
allowed-tools: Read, Grep, Bash
tags: testing, ci
context: local, ci
---

Run the project test suite and report results.

## Inputs

- `scope` (optional): Directory or file pattern to test
- `verbose` (required): Enable verbose output

## Gotchas

- Flaky tests should be retried once before failing
- Watch for tests that pass locally but fail in CI

## Steps

1. Detect the test runner from package.json or pyproject.toml
2. Run the test suite with the detected runner
3. Parse test output for failures
4. Generate a structured report

## Examples

- Run all tests: "/run_test"
- Run specific dir: "/run_test scope=src/api/"
"""
    path = ai_dir / "skills" / "test.md"
    path.write_text(content)
    return path


@pytest.fixture
def sample_rule_file(ai_dir):
    """Write a sample rule file and return its path."""
    content = """\
---
name: no-console-log
description: Never leave console.log in production code
globs: *.ts, *.tsx
tags: quality, typescript
enabled: true
---

Remove all `console.log` statements before committing.
Use a proper logging library instead.
"""
    path = ai_dir / "rules" / "no-console-log.md"
    path.write_text(content)
    return path


@pytest.fixture
def claude_native_skill_file(tmp_path):
    """Write a Claude-native SKILL.md and return its path."""
    content = """\
---
name: Example Claude Skill
description: An example skill in Claude-native format
version: 1.0.0
compatibility: claude-3, claude-4
license: MIT
---

This skill does something useful with Claude.

## Parameters

- `input` (required): The input to process
- `format` (optional): Output format

## Usage

- Basic usage: `example-skill input.txt`
- With format: `example-skill input.txt --format json`

## Caveats

- Only works with text files
- Large files may be slow
"""
    path = tmp_path / "SKILL.md"
    path.write_text(content)
    return path
