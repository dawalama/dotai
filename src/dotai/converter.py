"""Convert skills from multiple ecosystems to dotai format.

Supports:
- Claude-native SKILL.md (standalone skills)
- Claude Code plugins (.claude-plugin/plugin.json)
- Cursor plugins (.cursor-plugin/plugin.json)
- Gemini CLI extensions (gemini-extension.json)

Each ecosystem uses slightly different metadata, but all share a SKILL.md
convention with YAML frontmatter. This module detects, parses, and converts
them all into the universal dotai format.
"""

import json
import re
import shutil
import tomllib
from pathlib import Path

from .models import SkillCategory
from .utils import generate_id


# Keywords mapped to categories for inference from name + description
_CATEGORY_KEYWORDS: dict[str, SkillCategory] = {
    # Code quality
    "review": SkillCategory.CODE_QUALITY,
    "lint": SkillCategory.CODE_QUALITY,
    "refactor": SkillCategory.CODE_QUALITY,
    "clean": SkillCategory.CODE_QUALITY,
    "style": SkillCategory.CODE_QUALITY,
    # Verification
    "test": SkillCategory.VERIFICATION,
    "verify": SkillCategory.VERIFICATION,
    "validate": SkillCategory.VERIFICATION,
    "check": SkillCategory.VERIFICATION,
    "assert": SkillCategory.VERIFICATION,
    # Debugging
    "debug": SkillCategory.DEBUGGING,
    "investigate": SkillCategory.DEBUGGING,
    "diagnose": SkillCategory.DEBUGGING,
    "troubleshoot": SkillCategory.DEBUGGING,
    "fix": SkillCategory.DEBUGGING,
    "error": SkillCategory.DEBUGGING,
    # Deployment
    "deploy": SkillCategory.DEPLOYMENT,
    "ship": SkillCategory.DEPLOYMENT,
    "release": SkillCategory.DEPLOYMENT,
    "publish": SkillCategory.DEPLOYMENT,
    "ci": SkillCategory.DEPLOYMENT,
    "pipeline": SkillCategory.DEPLOYMENT,
    # Scaffolding
    "scaffold": SkillCategory.SCAFFOLDING,
    "generate": SkillCategory.SCAFFOLDING,
    "boilerplate": SkillCategory.SCAFFOLDING,
    "template": SkillCategory.SCAFFOLDING,
    "init": SkillCategory.SCAFFOLDING,
    "bootstrap": SkillCategory.SCAFFOLDING,
    "mvp": SkillCategory.SCAFFOLDING,
    "prototype": SkillCategory.SCAFFOLDING,
    # Data
    "query": SkillCategory.DATA,
    "dashboard": SkillCategory.DATA,
    "monitor": SkillCategory.DATA,
    "metric": SkillCategory.DATA,
    "analytics": SkillCategory.DATA,
    # Reference
    "docs": SkillCategory.REFERENCE,
    "documentation": SkillCategory.REFERENCE,
    "lookup": SkillCategory.REFERENCE,
    "reference": SkillCategory.REFERENCE,
    "search": SkillCategory.REFERENCE,
    # Maintenance
    "migrate": SkillCategory.MAINTENANCE,
    "upgrade": SkillCategory.MAINTENANCE,
    "cleanup": SkillCategory.MAINTENANCE,
    "maintenance": SkillCategory.MAINTENANCE,
    "ops": SkillCategory.MAINTENANCE,
    # Workflow (broad terms — lower priority, checked last)
    "plan": SkillCategory.WORKFLOW,
    "workflow": SkillCategory.WORKFLOW,
    "automate": SkillCategory.WORKFLOW,
    "process": SkillCategory.WORKFLOW,
    "guide": SkillCategory.WORKFLOW,
    "strategy": SkillCategory.WORKFLOW,
    "pricing": SkillCategory.WORKFLOW,
    "marketing": SkillCategory.WORKFLOW,
    "customer": SkillCategory.WORKFLOW,
    "community": SkillCategory.WORKFLOW,
    "growth": SkillCategory.WORKFLOW,
    "values": SkillCategory.WORKFLOW,
    "idea": SkillCategory.WORKFLOW,
}


def detect_skill_format(path: Path) -> str:
    """Detect whether a path is dotai, claude-native, a plugin, or unknown.

    Returns one of:
      "dotai", "claude-native", "claude-plugin", "cursor-plugin",
      "gemini-extension", or "unknown"
    """
    if not path.exists():
        return "unknown"

    # Plugin/extension directory detection (checked first)
    if path.is_dir():
        if (path / ".claude-plugin" / "plugin.json").exists():
            return "claude-plugin"
        if (path / ".cursor-plugin" / "plugin.json").exists():
            return "cursor-plugin"
        if (path / "gemini-extension.json").exists():
            return "gemini-extension"
        if (path / "SKILL.md").exists():
            return "claude-native"
        if (path / "main.md").exists():
            return "dotai"
        return "unknown"

    content = path.read_text()
    frontmatter = _extract_frontmatter(content)
    body = _extract_body(content)

    # dotai markers in frontmatter
    dotai_keys = {"trigger", "allowed-tools", "category"}
    if dotai_keys & set(frontmatter.keys()):
        return "dotai"

    # dotai markers in body
    if re.search(r"^## (Steps|Inputs)\b", body, re.MULTILINE):
        return "dotai"

    # Claude-native markers
    claude_keys = {"compatibility", "license"}
    if claude_keys & set(frontmatter.keys()):
        return "claude-native"

    # SKILL.md filename convention
    if path.name == "SKILL.md":
        return "claude-native"

    # Has scripts/ sibling directory
    if path.is_file() and (path.parent / "scripts").is_dir():
        return "claude-native"

    return "unknown"


def parse_claude_skill_md(path: Path) -> dict:
    """Extract frontmatter and body from a Claude SKILL.md file.

    Returns dict with keys: frontmatter (dict), body (str), path (Path),
    has_scripts (bool), has_references (bool), has_assets (bool).
    """
    if path.is_dir():
        skill_file = path / "SKILL.md"
        base_dir = path
    else:
        skill_file = path
        base_dir = path.parent

    content = skill_file.read_text()
    frontmatter = _extract_frontmatter(content)
    body = _extract_body(content)

    return {
        "frontmatter": frontmatter,
        "body": body,
        "path": skill_file,
        "base_dir": base_dir,
        "has_scripts": (base_dir / "scripts").is_dir(),
        "has_references": (base_dir / "references").is_dir(),
        "has_assets": (base_dir / "assets").is_dir(),
    }


def _detect_structure_in_body(body: str) -> dict:
    """Heuristic extraction of structure from free-form markdown.

    Looks for numbered lists, parameter sections, usage examples, and warnings.

    Returns dict with: steps, inputs, examples, gotchas, description, is_structured
    """
    steps: list[str] = []
    inputs: list[dict] = []
    examples: list[str] = []
    gotchas: list[str] = []
    description_lines: list[str] = []

    # Section header patterns (Claude-native conventions)
    section_patterns = {
        "inputs": re.compile(r"^##\s*(Parameters|Arguments|Configuration|Inputs)\b", re.IGNORECASE),
        "examples": re.compile(r"^##\s*(Usage|Examples?)\b", re.IGNORECASE),
        "gotchas": re.compile(r"^##\s*(Caveats|Warnings?|Notes?|Gotchas|Limitations?)\b", re.IGNORECASE),
        "steps": re.compile(r"^##\s*(Steps|Workflow|Instructions|How to use)\b", re.IGNORECASE),
    }

    current_section = "description"
    is_structured = False

    for line in body.split("\n"):
        # Check for section headers
        matched_section = None
        for section_name, pattern in section_patterns.items():
            if pattern.match(line.strip()):
                matched_section = section_name
                is_structured = True
                break

        if matched_section:
            current_section = matched_section
            continue

        # Skip other ## headers
        if line.strip().startswith("## "):
            current_section = "other"
            continue

        if current_section == "description":
            description_lines.append(line)
        elif current_section == "steps":
            match = re.match(r"\d+\.\s*(.+)", line.strip())
            if match:
                steps.append(match.group(1))
        elif current_section == "inputs":
            # Match `param` (type): description or - `param`: description
            match = re.match(r"-?\s*`(\w+)`\s*(?:\((\w+)\))?\s*:?\s*(.+)", line.strip())
            if match:
                inputs.append({
                    "name": match.group(1),
                    "required": match.group(2) == "required" if match.group(2) else False,
                    "description": match.group(3).strip(),
                })
        elif current_section == "examples":
            match = re.match(r"-\s*(.+)", line.strip())
            if match:
                examples.append(match.group(1))
            elif line.strip().startswith("```"):
                pass  # skip code fences
            elif line.strip():
                examples.append(line.strip())
        elif current_section == "gotchas":
            match = re.match(r"-\s*(.+)", line.strip())
            if match:
                gotchas.append(match.group(1))

    # If no explicit steps section but other structured sections were found,
    # look for numbered lists anywhere in body as fallback steps.
    # Don't do this for purely free-form content (avoids grabbing incidental numbered lists).
    if not steps and is_structured:
        for match in re.finditer(r"^\d+\.\s*(.+)$", body, re.MULTILINE):
            steps.append(match.group(1))

    description = "\n".join(description_lines).strip()
    # Take first paragraph as description if it's long
    if "\n\n" in description:
        description = description.split("\n\n")[0].strip()

    return {
        "steps": steps,
        "inputs": inputs,
        "examples": examples,
        "gotchas": gotchas,
        "description": description,
        "is_structured": is_structured,
    }


def _infer_category(name: str, description: str) -> SkillCategory:
    """Infer a skill category from its name and description.

    Scans name first (higher signal), then description. Falls back to workflow.
    """
    text = f"{name} {description}".lower()
    words = set(re.findall(r"[a-z]+", text))

    for keyword, category in _CATEGORY_KEYWORDS.items():
        if keyword in words:
            return category

    return SkillCategory.WORKFLOW


def convert_claude_to_dotai(source: Path, dest_dir: Path,
                            skill_name: str | None = None) -> Path:
    """Convert a Claude-native SKILL.md to dotai format.

    Args:
        source: Path to SKILL.md file or directory containing it
        dest_dir: Destination directory for the converted skill
        skill_name: Override skill name (derived from frontmatter if not given)

    Returns: Path to the created skill file/directory
    """
    parsed = parse_claude_skill_md(source)
    fm = parsed["frontmatter"]
    body = parsed["body"]

    name = skill_name or fm.get("name", source.stem if source.is_file() else source.name)
    skill_id = generate_id(name)
    description = fm.get("description", "")

    # Detect structure in body
    detected = _detect_structure_in_body(body)
    if not description:
        description = detected["description"]

    # Map Claude-native fields to dotai
    tags: list[str] = []
    if "compatibility" in fm:
        tags.extend(t.strip() for t in fm["compatibility"].split(",") if t.strip())
    if "tags" in fm:
        tags.extend(t.strip() for t in fm["tags"].split(",") if t.strip())

    # Infer category from name + description
    category = _infer_category(name, description)

    # Build frontmatter
    dotai_fm_lines = [
        f"name: {name}",
        f"trigger: /run_{skill_id}",
        f"category: {category.value}",
    ]
    if tags:
        dotai_fm_lines.append(f"tags: {', '.join(tags)}")
    if "license" in fm:
        dotai_fm_lines.append(f"# license: {fm['license']}")

    dotai_frontmatter = "\n".join(dotai_fm_lines)

    # Build body
    is_folder_skill = parsed["has_scripts"] or parsed["has_references"] or parsed["has_assets"]

    if detected["is_structured"]:
        # Write structured dotai format
        body_parts = [description, ""]

        if detected["inputs"]:
            body_parts.append("## Inputs")
            body_parts.append("")
            for inp in detected["inputs"]:
                req = "(required)" if inp.get("required") else "(optional)"
                body_parts.append(f"- `{inp['name']}` {req}: {inp['description']}")
            body_parts.append("")

        if detected["gotchas"]:
            body_parts.append("## Gotchas")
            body_parts.append("")
            for g in detected["gotchas"]:
                body_parts.append(f"- {g}")
            body_parts.append("")

        if detected["steps"]:
            body_parts.append("## Steps")
            body_parts.append("")
            for i, step in enumerate(detected["steps"], 1):
                body_parts.append(f"{i}. {step}")
            body_parts.append("")

        if detected["examples"]:
            body_parts.append("## Examples")
            body_parts.append("")
            for ex in detected["examples"]:
                body_parts.append(f"- {ex}")
            body_parts.append("")

        dotai_body = "\n".join(body_parts)
    else:
        # Free-form: keep as runbook
        dotai_body = f"{description}\n\n{body}" if description else body

    content = f"---\n{dotai_frontmatter}\n---\n\n{dotai_body.strip()}\n"

    dest_dir.mkdir(parents=True, exist_ok=True)

    if is_folder_skill:
        # Create folder-based skill
        skill_dir = dest_dir / skill_id
        skill_dir.mkdir(exist_ok=True)
        (skill_dir / "main.md").write_text(content)

        # Copy companion directories
        for dirname in ("scripts", "references", "assets"):
            src_sub = parsed["base_dir"] / dirname
            if src_sub.is_dir():
                dest_sub = skill_dir / dirname
                if dest_sub.exists():
                    shutil.rmtree(dest_sub)
                shutil.copytree(src_sub, dest_sub)

        return skill_dir
    else:
        # Single-file skill
        dest_file = dest_dir / f"{skill_id}.md"
        dest_file.write_text(content)
        return dest_file


def convert_skill_file(source: Path, dest_dir: Path) -> Path:
    """Public entry point: auto-detect format and convert if needed.

    If the source is already dotai format, copies it unchanged.
    If claude-native, converts to dotai format.
    If a plugin/extension, converts all skills within it.
    If unknown, copies as-is.

    Returns: Path to the destination file/directory
    """
    fmt = detect_skill_format(source)

    if fmt == "claude-native":
        return convert_claude_to_dotai(source, dest_dir)
    elif fmt in ("claude-plugin", "cursor-plugin", "gemini-extension"):
        results = convert_plugin_to_dotai(source, dest_dir)
        return results[0] if results else dest_dir
    else:
        # Copy as-is (dotai or unknown)
        dest_dir.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            dest = dest_dir / source.name
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(source, dest)
            return dest
        else:
            dest = dest_dir / source.name
            shutil.copy2(source, dest)
            return dest


# --- Plugin / extension support ---

def parse_plugin_manifest(path: Path) -> dict:
    """Parse a plugin/extension directory and return normalized metadata.

    Works with Claude plugins, Cursor plugins, and Gemini extensions.

    Returns dict with: format, name, description, author, skills (list of Paths),
    commands (list of Paths), agents (list of Paths), rules (list of Paths),
    has_hooks, has_mcp.
    """
    fmt = detect_skill_format(path)
    manifest: dict = {}

    if fmt == "claude-plugin":
        manifest_path = path / ".claude-plugin" / "plugin.json"
        manifest = json.loads(manifest_path.read_text())
    elif fmt == "cursor-plugin":
        manifest_path = path / ".cursor-plugin" / "plugin.json"
        manifest = json.loads(manifest_path.read_text())
    elif fmt == "gemini-extension":
        manifest_path = path / "gemini-extension.json"
        manifest = json.loads(manifest_path.read_text())
    else:
        return {"format": "unknown", "name": path.name, "description": "",
                "author": "", "skills": [], "commands": [], "agents": [],
                "rules": [], "has_hooks": False, "has_mcp": False}

    # Normalize author
    author_raw = manifest.get("author", {})
    if isinstance(author_raw, dict):
        author = author_raw.get("name", "")
    else:
        author = str(author_raw)

    # Discover skills (all three use skills/*/SKILL.md)
    skills: list[Path] = []
    skills_dir = path / "skills"
    if skills_dir.is_dir():
        for sub in sorted(skills_dir.iterdir()):
            if sub.is_dir() and (sub / "SKILL.md").exists():
                skills.append(sub / "SKILL.md")

    # Discover commands
    commands: list[Path] = []
    commands_dir = path / "commands"
    if commands_dir.is_dir():
        for f in sorted(commands_dir.rglob("*")):
            if f.is_file() and f.suffix in (".md", ".toml"):
                commands.append(f)

    # Discover agents
    agents: list[Path] = []
    agents_dir = path / "agents"
    if agents_dir.is_dir():
        for f in sorted(agents_dir.glob("*.md")):
            agents.append(f)

    # Discover Cursor .mdc rules
    rules: list[Path] = []
    if fmt == "cursor-plugin":
        rules_dir = path / "rules"
        if rules_dir.is_dir():
            for f in sorted(rules_dir.glob("*.mdc")):
                rules.append(f)

    # Check for hooks and MCP
    has_hooks = (path / "hooks").is_dir()
    has_mcp = (path / ".mcp.json").exists() or (path / "mcp.json").exists()
    if fmt == "gemini-extension":
        mcp_servers = manifest.get("mcpServers", {})
        has_mcp = has_mcp or bool(mcp_servers)

    return {
        "format": fmt,
        "name": manifest.get("name", path.name),
        "description": manifest.get("description", ""),
        "author": author,
        "skills": skills,
        "commands": commands,
        "agents": agents,
        "rules": rules,
        "has_hooks": has_hooks,
        "has_mcp": has_mcp,
    }


def convert_plugin_to_dotai(source: Path, dest_dir: Path,
                            skill_filter: str | None = None,
                            include_agents: bool = False,
                            include_rules: bool = False) -> list[Path]:
    """Convert a plugin/extension directory into dotai skills (and optionally roles/rules).

    Args:
        source: Path to the plugin/extension directory
        dest_dir: Destination directory for converted skills
        skill_filter: If set, only convert the skill with this name
        include_agents: If True, also convert agents to dotai roles
        include_rules: If True, also convert Cursor .mdc rules to dotai rules

    Returns: List of paths to created files/directories
    """
    parsed = parse_plugin_manifest(source)
    results: list[Path] = []
    warnings: list[str] = []

    dest_dir.mkdir(parents=True, exist_ok=True)

    # Convert skills
    for skill_path in parsed["skills"]:
        skill_dir = skill_path.parent
        skill_name = skill_dir.name

        if skill_filter and skill_name != skill_filter:
            continue

        result = convert_claude_to_dotai(skill_dir, dest_dir, skill_name)
        results.append(result)

    # Convert commands
    for cmd_path in parsed["commands"]:
        cmd_name = cmd_path.stem
        if skill_filter and cmd_name != skill_filter:
            continue

        if cmd_path.suffix == ".toml":
            result = _convert_gemini_command(cmd_path, dest_dir)
            if result:
                results.append(result)
        elif cmd_path.suffix == ".md":
            # Treat .md commands like claude-native skills
            result = convert_claude_to_dotai(cmd_path, dest_dir, cmd_name)
            results.append(result)

    # Convert agents to roles
    if include_agents and parsed["agents"]:
        roles_dir = dest_dir.parent / "roles"
        roles_dir.mkdir(parents=True, exist_ok=True)
        for agent_path in parsed["agents"]:
            result = _convert_agent_to_role(agent_path, roles_dir)
            if result:
                results.append(result)

    # Convert Cursor .mdc rules
    if include_rules and parsed["rules"]:
        rules_dir = dest_dir.parent / "rules"
        rules_dir.mkdir(parents=True, exist_ok=True)
        for rule_path in parsed["rules"]:
            result = _convert_cursor_rule(rule_path, rules_dir)
            if result:
                results.append(result)

    # Warn about non-convertible artifacts
    if parsed["has_hooks"]:
        warnings.append("hooks (not convertible to dotai)")
    if parsed["has_mcp"]:
        warnings.append("MCP server configs (not convertible to dotai)")

    return results


def _convert_gemini_command(source: Path, dest_dir: Path) -> Path | None:
    """Convert a Gemini CLI .toml command file to a dotai skill.

    Gemini commands are TOML files with 'description' and 'prompt' fields,
    plus template syntax: {{args}}, !{shell}, @{file}.
    """
    try:
        data = tomllib.loads(source.read_text())
    except Exception:
        return None

    prompt = data.get("prompt", "")
    description = data.get("description", "")

    # Derive name from file path (e.g. commands/git/commit.toml -> git-commit)
    rel = source.relative_to(source.parent)
    # Walk up to find commands/ root
    parts = list(source.parts)
    try:
        cmd_idx = parts.index("commands")
        name_parts = parts[cmd_idx + 1:]
    except ValueError:
        name_parts = [source.stem]

    # Strip .toml extension from last part
    name_parts[-1] = Path(name_parts[-1]).stem
    name = "-".join(name_parts)
    skill_id = generate_id(name)

    # Note template variables in the body
    body_lines = []
    if "{{args}}" in prompt or "{{" in prompt:
        body_lines.append("<!-- Note: {{args}} is replaced with user arguments -->")
        body_lines.append("")
    if "!{" in prompt:
        body_lines.append("<!-- Note: !{command} blocks execute shell commands -->")
        body_lines.append("")
    if "@{" in prompt:
        body_lines.append("<!-- Note: @{path} blocks inject file contents -->")
        body_lines.append("")
    body_lines.append(prompt)

    category = _infer_category(name, description)

    content = f"""---
name: {name}
trigger: /run_{skill_id}
category: {category.value}
# source-format: gemini-command
---

{description}

{"".join(ln + chr(10) for ln in body_lines)}"""

    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_file = dest_dir / f"{skill_id}.md"
    dest_file.write_text(content)
    return dest_file


def _convert_agent_to_role(source: Path, roles_dir: Path) -> Path | None:
    """Convert a plugin agent .md file to a dotai role.

    Agent files have frontmatter with name, description, tools, model, color.
    The body becomes the role's persona.
    """
    content = source.read_text()
    frontmatter = _extract_frontmatter(content)
    body = _extract_body(content)

    name = frontmatter.get("name", source.stem)
    description = frontmatter.get("description", "")
    role_id = generate_id(name)

    role_content = f"""---
name: {name}
description: {description}
tags: imported
---

{body.strip()}
"""

    roles_dir.mkdir(parents=True, exist_ok=True)
    dest = roles_dir / f"{role_id}.md"
    dest.write_text(role_content)
    return dest


def _convert_cursor_rule(source: Path, rules_dir: Path) -> Path | None:
    """Convert a Cursor .mdc rule file to a dotai rule.

    .mdc files have frontmatter with description, globs, alwaysApply.
    """
    content = source.read_text()
    frontmatter = _extract_frontmatter(content)
    body = _extract_body(content)

    name = source.stem.replace("-", " ").replace("_", " ").title()
    description = frontmatter.get("description", "")
    globs = frontmatter.get("globs", "")
    rule_id = generate_id(source.stem)

    fm_lines = [
        f"name: {name}",
        f"description: {description}",
    ]
    if globs:
        fm_lines.append(f"globs: {globs}")
    fm_lines.append("tags: imported, cursor")

    rule_content = f"""---
{chr(10).join(fm_lines)}
---

{body.strip()}
"""

    rules_dir.mkdir(parents=True, exist_ok=True)
    dest = rules_dir / f"{rule_id}.md"
    dest.write_text(rule_content)
    return dest


# --- Internal helpers ---

def _extract_frontmatter(content: str) -> dict[str, str]:
    """Extract YAML-like frontmatter from markdown content."""
    frontmatter: dict[str, str] = {}
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].strip().split("\n"):
                if ":" in line:
                    key, value = line.split(":", 1)
                    frontmatter[key.strip().lower()] = value.strip()
    return frontmatter


def _extract_body(content: str) -> str:
    """Extract body (after frontmatter) from markdown content."""
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            return parts[2].strip()
    return content.strip()
