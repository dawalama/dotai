"""Role parsing and management."""

import re
from pathlib import Path

from .models import GlobalConfig, KnowledgeNode, NodeType, Role
from .utils import generate_id as generate_role_id


def parse_role_file(file_path: Path, scope: str = "global") -> Role | None:
    """Parse a role from a markdown file.

    Expected format:
    ---
    name: Role Name
    description: One-line description
    tags: tag1, tag2
    ---

    You are a [persona description]...

    ## Principles

    - Principle one
    - Principle two

    ## Anti-patterns

    - Thing to avoid
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
    description = frontmatter.get("description", "")
    tags = [t.strip() for t in frontmatter.get("tags", "").split(",") if t.strip()]

    # Parse body
    persona_lines: list[str] = []
    principles: list[str] = []
    anti_patterns: list[str] = []
    current_section = "persona"

    for line in body.split("\n"):
        line_lower = line.lower().strip()

        if line_lower.startswith("## principles") or line_lower.startswith("## core principles"):
            current_section = "principles"
            continue
        elif line_lower.startswith("## anti-pattern") or line_lower.startswith("## avoid"):
            current_section = "anti_patterns"
            continue
        elif line.startswith("## "):
            current_section = "other"
            continue

        if current_section == "persona":
            persona_lines.append(line)
        elif current_section == "principles":
            match = re.match(r"[-*]\s+(.+)", line)
            if match:
                principles.append(match.group(1))
        elif current_section == "anti_patterns":
            match = re.match(r"[-*]\s+(.+)", line)
            if match:
                anti_patterns.append(match.group(1))

    persona = "\n".join(persona_lines).strip()
    if not description:
        # Use first sentence of persona as description
        first_sentence = persona.split(".")[0] if persona else name
        description = first_sentence[:120]

    return Role(
        id=generate_role_id(name),
        name=name,
        description=description,
        persona=persona,
        principles=principles,
        anti_patterns=anti_patterns,
        tags=tags,
        file_path=file_path,
        scope=scope,
    )


def load_roles_from_dir(roles_dir: Path, scope: str = "global") -> list[Role]:
    """Load all roles from a directory."""
    roles = []
    if not roles_dir.exists():
        return roles

    for md_file in sorted(roles_dir.glob("*.md")):
        role = parse_role_file(md_file, scope)
        if role:
            roles.append(role)

    return roles


def load_all_roles(config: GlobalConfig) -> list[Role]:
    """Load all roles from global and project directories."""
    roles = []

    # Global roles
    roles.extend(load_roles_from_dir(config.global_roles_path, "global"))

    # Project roles
    for project in config.projects:
        roles.extend(load_roles_from_dir(project.roles_path, project.name))

    return roles


def build_roles_node(roles: list[Role], category_name: str, category_id: str) -> KnowledgeNode:
    """Build a knowledge node for a collection of roles."""
    children = []

    for role in roles:
        children.append(KnowledgeNode(
            id=f"role_{role.id}",
            name=role.name,
            node_type=NodeType.ROLE,
            summary=role.description,
            file_path=role.file_path,
            tags=role.tags,
            metadata={"scope": role.scope},
        ))

    return KnowledgeNode(
        id=category_id,
        name=category_name,
        node_type=NodeType.CATEGORY,
        summary=f"{len(roles)} roles available",
        children=children,
    )


def create_role_template(name: str) -> str:
    """Generate a template for a new role."""
    return f"""---
name: {name}
description: One-line description of this role's perspective
tags:
---

You are a [describe the persona]. Your job is to [describe the mission].

## Principles

- First principle
- Second principle

## Anti-patterns

- Thing this role should never do
"""
