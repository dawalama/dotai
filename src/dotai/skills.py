"""Skill parsing and management.

Supports two skill formats:

1. Single-file skills:  ~/.ai/skills/review.md
2. Folder-based skills: ~/.ai/skills/deploy/
                           main.md        # Skill definition (frontmatter + body)
                           scripts/       # Helper scripts the agent can invoke
                           assets/        # Templates, reference docs, configs
                           config.json    # User-specific configuration overrides

Folder-based skills enable progressive disclosure — the main.md gives the agent
the high-level workflow, while scripts/ and assets/ provide concrete tooling
that keeps token usage efficient (the agent reads only what it needs).
"""

import json
import re
from pathlib import Path

from .models import GlobalConfig, KnowledgeNode, NodeType, Skill, SkillCategory
from .utils import generate_id as generate_skill_id


# Map category strings to enum values (case-insensitive, with aliases)
_CATEGORY_ALIASES: dict[str, SkillCategory] = {}
for cat in SkillCategory:
    _CATEGORY_ALIASES[cat.value] = cat
    _CATEGORY_ALIASES[cat.name.lower()] = cat
# Common aliases
_CATEGORY_ALIASES.update({
    "ref": SkillCategory.REFERENCE,
    "docs": SkillCategory.REFERENCE,
    "test": SkillCategory.VERIFICATION,
    "testing": SkillCategory.VERIFICATION,
    "validate": SkillCategory.VERIFICATION,
    "monitor": SkillCategory.DATA,
    "monitoring": SkillCategory.DATA,
    "query": SkillCategory.DATA,
    "automate": SkillCategory.WORKFLOW,
    "automation": SkillCategory.WORKFLOW,
    "scaffold": SkillCategory.SCAFFOLDING,
    "generate": SkillCategory.SCAFFOLDING,
    "boilerplate": SkillCategory.SCAFFOLDING,
    "review": SkillCategory.CODE_QUALITY,
    "lint": SkillCategory.CODE_QUALITY,
    "quality": SkillCategory.CODE_QUALITY,
    "deploy": SkillCategory.DEPLOYMENT,
    "ship": SkillCategory.DEPLOYMENT,
    "release": SkillCategory.DEPLOYMENT,
    "ci": SkillCategory.DEPLOYMENT,
    "debug": SkillCategory.DEBUGGING,
    "investigate": SkillCategory.DEBUGGING,
    "ops": SkillCategory.MAINTENANCE,
    "migrate": SkillCategory.MAINTENANCE,
    "cleanup": SkillCategory.MAINTENANCE,
})


def _parse_category(raw: str) -> SkillCategory | None:
    """Resolve a category string to a SkillCategory enum value."""
    return _CATEGORY_ALIASES.get(raw.strip().lower())


def _parse_list_field(raw: str) -> list[str]:
    """Parse a comma-separated or YAML-style list from frontmatter."""
    return [item.strip().strip("[]") for item in raw.split(",") if item.strip()]


def _load_skill_config(skill_dir: Path) -> dict:
    """Load config.json from a folder-based skill, if it exists."""
    config_path = skill_dir / "config.json"
    if config_path.exists():
        try:
            return json.loads(config_path.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


SOURCES_FILE = ".dotai-sources.json"


def load_sources(skills_dir: Path) -> dict[str, dict]:
    """Load the source manifest for a skills directory.

    Returns a dict mapping skill filename/dirname to source info:
      {"mvp.md": {"url": "https://...", "type": "git"}, ...}
    """
    path = skills_dir / SOURCES_FILE
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_sources(skills_dir: Path, sources: dict[str, dict]) -> None:
    """Save the source manifest."""
    skills_dir.mkdir(parents=True, exist_ok=True)
    path = skills_dir / SOURCES_FILE
    path.write_text(json.dumps(sources, indent=2) + "\n")


def record_source(skills_dir: Path, skill_key: str, source_url: str,
                  source_type: str = "git") -> None:
    """Record where a skill was installed from."""
    sources = load_sources(skills_dir)
    sources[skill_key] = {"url": source_url, "type": source_type}
    save_sources(skills_dir, sources)


def parse_skill_file(file_path: Path, scope: str = "global",
                     assets_dir: Path | None = None,
                     skill_config: dict | None = None) -> Skill | None:
    """Parse a skill from a markdown file.

    Supports both structured format (## Inputs/Steps/Examples sections)
    and runbook format (free-form markdown body with embedded code blocks).

    Frontmatter fields:
      name, trigger, role, allowed-tools, tags, category, gotchas, context
    """
    if not file_path.exists():
        return None

    content = file_path.read_text()

    # Parse frontmatter
    frontmatter: dict[str, str] = {}
    body = content

    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            fm_content = parts[1].strip()
            body = parts[2].strip()

            for line in fm_content.split("\n"):
                if ":" in line:
                    key, value = line.split(":", 1)
                    frontmatter[key.strip().lower()] = value.strip()

    name = frontmatter.get("name", file_path.stem.replace("-", " ").replace("_", " ").title())
    trigger = frontmatter.get("trigger")
    role = frontmatter.get("role")
    tags = _parse_list_field(frontmatter.get("tags", ""))
    category = _parse_category(frontmatter["category"]) if "category" in frontmatter else None
    gotchas = _parse_list_field(frontmatter.get("gotchas", ""))
    context = _parse_list_field(frontmatter.get("context", ""))

    # Parse allowed-tools
    allowed_tools = _parse_list_field(frontmatter.get("allowed-tools", ""))

    # Parse body sections
    description = ""
    inputs: list[dict] = []
    steps: list[str] = []
    examples: list[str] = []
    raw_body = ""
    body_gotchas: list[str] = []

    # Check if this is a runbook-style skill (has ```bash blocks or ## Step N)
    is_runbook = bool(re.search(r"```\w+|## Step \d", body))

    if is_runbook:
        # Runbook: extract description from first paragraph, keep rest as raw_body
        paragraphs = body.split("\n\n", 1)
        description = paragraphs[0].strip()
        raw_body = paragraphs[1].strip() if len(paragraphs) > 1 else ""
    else:
        # Structured: parse into sections
        current_section = "description"

        for line in body.split("\n"):
            line_lower = line.lower().strip()

            if line_lower.startswith("## inputs"):
                current_section = "inputs"
                continue
            elif line_lower.startswith("## steps"):
                current_section = "steps"
                continue
            elif line_lower.startswith("## examples"):
                current_section = "examples"
                continue
            elif line_lower.startswith("## gotchas"):
                current_section = "gotchas"
                continue
            elif line.startswith("## "):
                current_section = "other"
                continue

            if current_section == "description":
                description += line + "\n"
            elif current_section == "inputs":
                match = re.match(r"-\s*`(\w+)`\s*\((required|optional)\):\s*(.+)", line)
                if match:
                    inputs.append({
                        "name": match.group(1),
                        "required": match.group(2) == "required",
                        "description": match.group(3),
                    })
            elif current_section == "steps":
                match = re.match(r"\d+\.\s*(.+)", line)
                if match:
                    steps.append(match.group(1))
            elif current_section == "examples":
                match = re.match(r"-\s*(.+)", line)
                if match:
                    examples.append(match.group(1))
            elif current_section == "gotchas":
                match = re.match(r"-\s*(.+)", line)
                if match:
                    body_gotchas.append(match.group(1))

    # Merge gotchas from frontmatter and body
    all_gotchas = gotchas + body_gotchas

    return Skill(
        id=generate_skill_id(name),
        name=name,
        description=description.strip(),
        category=category,
        trigger=trigger,
        role=role,
        allowed_tools=allowed_tools,
        inputs=inputs,
        steps=steps,
        examples=examples,
        gotchas=all_gotchas,
        context=context,
        tags=tags,
        file_path=file_path,
        assets_dir=assets_dir,
        config=skill_config or {},
        scope=scope,
        raw_body=raw_body,
    )


def load_skills_from_dir(skills_dir: Path, scope: str = "global") -> list[Skill]:
    """Load all skills from a directory.

    Supports both single-file skills (*.md) and folder-based skills
    (directories containing a main.md).
    """
    skills = []

    if not skills_dir.exists():
        return skills

    sources = load_sources(skills_dir)

    # Single-file skills
    for md_file in sorted(skills_dir.glob("*.md")):
        skill = parse_skill_file(md_file, scope)
        if skill:
            src = sources.get(md_file.name, {})
            skill.source = src.get("url", "")
            skills.append(skill)

    # Folder-based skills (directories with main.md)
    for item in sorted(skills_dir.iterdir()):
        if item.is_dir() and (item / "main.md").exists():
            skill_config = _load_skill_config(item)
            skill = parse_skill_file(
                item / "main.md",
                scope=scope,
                assets_dir=item,
                skill_config=skill_config,
            )
            if skill:
                src = sources.get(item.name, {})
                skill.source = src.get("url", "")
                skills.append(skill)

    return skills


def load_all_skills(config: GlobalConfig) -> list[Skill]:
    """Load all skills from global and project directories."""
    skills = []

    # Global skills
    skills.extend(load_skills_from_dir(config.global_skills_path, "global"))

    # Project skills
    for project in config.projects:
        skills.extend(load_skills_from_dir(project.skills_path, project.name))

    return skills


def build_skills_node(skills: list[Skill], category_name: str, category_id: str) -> KnowledgeNode:
    """Build a knowledge node for a collection of skills."""
    children = []

    for skill in skills:
        trigger_info = f" ({skill.trigger})" if skill.trigger else ""
        cat_info = f" [{skill.category.value}]" if skill.category else ""
        children.append(KnowledgeNode(
            id=f"skill_{skill.id}",
            name=skill.name + trigger_info + cat_info,
            node_type=NodeType.SKILL,
            summary=skill.description[:100] + "..." if len(skill.description) > 100 else skill.description,
            file_path=skill.file_path,
            tags=skill.tags,
            metadata={
                "trigger": skill.trigger,
                "role": skill.role,
                "scope": skill.scope,
                "category": skill.category.value if skill.category else None,
                "folder_skill": skill.is_folder_skill,
            },
        ))

    return KnowledgeNode(
        id=category_id,
        name=category_name,
        node_type=NodeType.CATEGORY,
        summary=f"{len(skills)} skills available",
        children=children,
    )


def create_skill_template(name: str, trigger: str | None = None,
                          role: str | None = None,
                          category: str | None = None,
                          folder: bool = False) -> str | dict[str, str]:
    """Generate a template for a new skill.

    If folder=True, returns a dict of {filename: content} for a folder-based skill.
    Otherwise returns a single markdown string.
    """
    trigger_line = f"trigger: {trigger}" if trigger else "# trigger: /command"
    role_line = f"role: {role}" if role else "# role: reviewer"
    category_line = f"category: {category}" if category else "# category: workflow"

    main_content = f"""---
name: {name}
{trigger_line}
{role_line}
{category_line}
# allowed-tools: Read, Grep, Glob, Bash
# context: local, ci, production
tags:
---

Brief description of what this skill does and when to use it.

## Inputs

- `param1` (required): Description of required parameter
- `param2` (optional): Description of optional parameter

## Gotchas

- Common failure point that the agent should watch for
- Edge case that often causes issues

## Steps

1. First, do this
2. Then, do that
3. Finally, complete with this

## Examples

- Example: "Run this skill with param1=value"
"""

    if not folder:
        return main_content

    return {
        "main.md": main_content,
        "config.json": json.dumps({"version": "1.0"}, indent=2) + "\n",
        "scripts/.gitkeep": "",
        "assets/.gitkeep": "",
    }


def install_skill_from_repo(repo_url: str, dest_dir: Path,
                            skill_name: str | None = None) -> Path:
    """Install a skill from a git repository.

    Clones the repo into a temporary location and copies the skill
    (or entire repo if it IS a skill) into the destination directory.

    Returns the path to the installed skill.
    """
    import subprocess
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp) / "repo"
        subprocess.run(
            ["git", "clone", "--depth", "1", repo_url, str(tmp_path)],
            check=True,
            capture_output=True,
        )

        # Determine what we're installing
        if skill_name:
            # Install a specific skill from the repo
            source = tmp_path / skill_name
            if not source.exists():
                # Try skills/ subdirectory
                source = tmp_path / "skills" / skill_name
            if not source.exists():
                raise FileNotFoundError(
                    f"Skill '{skill_name}' not found in {repo_url}"
                )
        else:
            # Check if the repo root IS a skill (has main.md or a single .md)
            if (tmp_path / "main.md").exists():
                source = tmp_path
                skill_name = tmp_path.name
            else:
                # Look for a skills/ directory
                skills_in_repo = tmp_path / "skills"
                if skills_in_repo.exists():
                    source = skills_in_repo
                    skill_name = "imported"
                else:
                    # Treat the whole repo as a collection of .md skills
                    source = tmp_path
                    skill_name = "imported"

        dest = dest_dir / (skill_name or "imported")

        if source.is_file():
            # Single file skill
            import shutil
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / source.name
            shutil.copy2(source, dest)
        elif source.is_dir():
            import shutil
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(source, dest, dirs_exist_ok=True)
            # Clean up git artifacts
            git_dir = dest / ".git"
            if git_dir.exists():
                shutil.rmtree(git_dir)
        else:
            raise FileNotFoundError(f"Could not find skill source in {repo_url}")

    return dest
