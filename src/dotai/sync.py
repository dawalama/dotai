"""Agent sync — generate bootstrap files that teach any AI agent about ~/.ai/.

This module generates agent-specific bootstrap files that tell coding agents
how to find and use the knowledge in ~/.ai/. Supports:
  - Claude Code:  CLAUDE.md + .claude/skills/ (native slash commands)
  - Cursor:       .cursorrules
  - Gemini CLI:   GEMINI.md
  - Generic:      AGENTS.md (works with Codex, Copilot, etc.)
"""

import shutil
from pathlib import Path

from .models import GlobalConfig, Skill, Role
from .roles import load_all_roles
from .rules import load_rules_from_dir, resolve_rules_for_project
from .skills import load_all_skills


def generate_primer(config: GlobalConfig, project_name: str | None = None,
                    project_path: Path | None = None,
                    compact: bool = False) -> str:
    """Generate a universal primer that any agent can consume.

    This is the core knowledge block — it tells the agent what ~/.ai/ is,
    what's available, and how to use it. When project_path is given, also
    discovers local rules in <project>/.ai/rules/.

    When compact=True, emits summaries with file path pointers instead of
    full inline content. Use for agents that can read files (Claude Code).
    """
    ai_dir = config.global_ai_dir
    roles = load_all_roles(config)
    rules = resolve_rules_for_project(config, project_name)
    skills = load_all_skills(config)

    # Discover local project rules that aren't managed by dotai
    if project_path:
        local_rules_dir = project_path / ".ai" / "rules"
        local_rules = load_rules_from_dir(local_rules_dir, project_name or "local")
        # Merge: local rules that aren't already in the resolved set
        existing_ids = {r.id for r in rules}
        for lr in local_rules:
            if lr.id not in existing_ids and lr.enabled:
                rules.append(lr)

    # Filter to project scope if specified
    if project_name:
        project_roles = [r for r in roles if r.scope == project_name or r.scope == "global"]
        project_skills = [s for s in skills if s.scope == project_name or s.scope == "global"]
    else:
        project_roles = roles
        project_skills = skills

    project_rules = rules

    lines = [
        "# AI Knowledge Base (~/.ai/)",
        "",
        "This project uses a structured knowledge system at `~/.ai/` with project-level",
        "overrides in `.ai/`. Before starting work, read the relevant context files.",
        "",
        "## Structure",
        "",
        "```",
        "~/.ai/",
        "  rules.md          # Coding rules, conventions, and lessons learned",
        "  roles/            # Cognitive modes (personas for different tasks)",
        "  skills/           # Reusable workflows (slash commands)",
        "  tools/            # Python tool implementations",
        "```",
        "",
        "Project-specific overrides live in `<project>/.ai/` with the same structure.",
        "Project rules take precedence over global rules.",
        "",
    ]

    # List active rules
    if project_rules:
        lines.append("## Active Rules")
        lines.append("")
        if compact:
            # Summary table with file pointers — agent reads full rule on demand
            for rule in project_rules:
                globs = f" (applies to: `{', '.join(rule.globs)}`)" if rule.globs else ""
                source = f" — `{rule.file_path}`" if rule.file_path else ""
                lines.append(f"- **{rule.name}**: {rule.description}{globs}{source}")
            lines.append("")
        else:
            # Full inline content for agents that can't read files
            for rule in project_rules:
                lines.append(rule.to_prompt())
                lines.append("")
        lines.append("")

    # List available roles
    if project_roles:
        lines.append("## Available Roles")
        lines.append("")
        for role in project_roles:
            scope_tag = f" [{role.scope}]" if role.scope != "global" else ""
            lines.append(f"- **{role.name}**{scope_tag}: {role.description}")
        lines.append("")

        if compact:
            # Pointer to role files — agent reads on demand when composing
            lines.append("To adopt a role, read its file from `~/.ai/roles/` and follow its persona.")
            lines.append("")
        else:
            # Full inline content for agents that can't read files
            lines.append("To adopt a role, follow its persona below.")
            lines.append("")
            for role in project_roles:
                lines.append(f"### Role: {role.name}")
                lines.append("")
                lines.append(role.to_prompt())
                lines.append("")

    # List available skills, grouped by category
    if project_skills:
        lines.append("## Available Skills")
        lines.append("")

        # Group by category
        from .models import SkillCategory
        categorized: dict[str, list] = {}
        uncategorized: list = []
        for skill in project_skills:
            if skill.category:
                cat_name = skill.category.value
                categorized.setdefault(cat_name, []).append(skill)
            else:
                uncategorized.append(skill)

        for cat_name in sorted(categorized.keys()):
            lines.append(f"### {cat_name.replace('-', ' ').title()}")
            lines.append("")
            for skill in categorized[cat_name]:
                trigger = f" `{skill.trigger}`" if skill.trigger else ""
                role_ref = f" (role: {skill.role})" if skill.role else ""
                ctx = f" [context: {', '.join(skill.context)}]" if skill.context else ""
                lines.append(f"- **{skill.name}**{trigger}{role_ref}{ctx}: {skill.description[:80]}")
            lines.append("")

        if uncategorized:
            for skill in uncategorized:
                trigger = f" `{skill.trigger}`" if skill.trigger else ""
                role_ref = f" (role: {skill.role})" if skill.role else ""
                lines.append(f"- **{skill.name}**{trigger}{role_ref}: {skill.description[:80]}")
            lines.append("")

        if compact:
            # Claude Code has native slash commands — no need for full inline definitions
            lines.append("Skills are available as slash commands (e.g. `/run_review`).")
            lines.append("Folder-based skills may include helper scripts in `scripts/` — prefer these over writing from scratch.")
            lines.append("")
        else:
            lines.append("To run a skill, follow its steps below.")
            lines.append("Folder-based skills may include helper scripts in `scripts/` — prefer these over writing from scratch.")
            lines.append("")

            # Include full skill definitions so file-based agents (Cursor, etc.) have everything inline
            lines.append("## Skill Definitions")
            lines.append("")
            for skill in project_skills:
                lines.append(skill.to_prompt())
                lines.append("")
                lines.append("---")
                lines.append("")

    # How to use
    lines.extend([
        "## How to Use",
        "",
        "1. **Start of session**: Read `~/.ai/rules.md` and the project's `.ai/rules.md`",
        "2. **Before a task**: Check if a relevant skill exists and adopt its role",
        "3. **When unsure**: The rules contain conventions, corrections, and project-specific guidance",
        "",
        "## Composing Skills with Roles",
        "",
        "When the user writes `/<skill> as <role>`, adopt the role's full persona",
        "before executing the skill's steps. The role shapes *how* you think;",
        "the skill defines *what* you do.",
        "",
        "Examples:",
        "- `/run_review as qa` — run the Code Review skill while thinking like a QA Engineer",
        "- `/run_review as paranoid-reviewer` — review code as a paranoid staff engineer focused on security",
        "- `/run_techdebt as debugger` — hunt tech debt with a debugger's systematic mindset",
        "- `/run_review` (no role) — run the skill with its default role, or no persona if none is set",
        "",
        "To compose: find the matching role from **Available Roles** above,",
        "adopt its persona and principles, then execute the skill's steps.",
        "The role's anti-patterns become things to watch for during execution.",
        "",
    ])

    return "\n".join(lines)


def generate_claude_md_section(config: GlobalConfig, project_name: str | None = None,
                               project_path: Path | None = None) -> str:
    """Generate a section to append to CLAUDE.md.

    Uses compact mode since Claude Code can read files and has native
    slash commands — no need for full inline content.
    """
    primer = generate_primer(config, project_name, project_path, compact=True)
    return f"""
# AI Context

{primer}

Read `~/.ai/rules.md` at the start of every conversation.
"""


def generate_cursorrules(config: GlobalConfig, project_name: str | None = None,
                         project_path: Path | None = None) -> str:
    """Generate .cursorrules content."""
    return generate_primer(config, project_name, project_path)


def generate_gemini_md(config: GlobalConfig, project_name: str | None = None,
                       project_path: Path | None = None) -> str:
    """Generate GEMINI.md for Gemini CLI.

    Gemini CLI discovers GEMINI.md files in the project root and
    concatenates them into context. It also reads ~/.gemini/GEMINI.md
    for global instructions.
    """
    primer = generate_primer(config, project_name, project_path)
    return f"""# Project Context

{primer}

This file is auto-generated by dotai. Do not edit manually.
Run `dotai sync` to regenerate.
"""


def generate_agents_md(config: GlobalConfig, project_name: str | None = None,
                       project_path: Path | None = None) -> str:
    """Generate AGENTS.md (generic agent bootstrap)."""
    primer = generate_primer(config, project_name, project_path)
    return f"""# Agent Instructions

{primer}

This file is auto-generated by dotai. Do not edit manually.
Run `dotai sync` to regenerate.
"""


def generate_claude_skill_md(skill: Skill, all_roles: list[Role]) -> str:
    """Generate a SKILL.md file for a Claude Code native slash command.

    This turns a dotai skill into a Claude Code skill that appears in the
    slash command menu. Supports role composition via arguments:
      /run_review             — runs with default role (or no role)
      /run_review as qa       — runs with the qa role persona
    """
    # Build trigger name (strip leading /)
    trigger = skill.trigger or f"/run_{skill.id}"
    cmd_name = trigger.lstrip("/")

    # YAML frontmatter
    lines = ["---"]
    lines.append(f"name: {cmd_name}")
    lines.append(f"description: {skill.description}")
    lines.append('argument-hint: "[as <role>]"')
    if skill.allowed_tools:
        lines.append(f"allowed-tools: {', '.join(skill.allowed_tools)}")
    lines.append("---")
    lines.append("")

    # Role composition instructions
    lines.append("<!-- Auto-generated by dotai. Run `dotai sync` to regenerate. -->")
    lines.append("")

    # Build available roles reference
    role_ids = [r.id for r in all_roles]
    lines.append("## Role Composition")
    lines.append("")
    lines.append("If the user passed `as <role>` in the arguments, adopt that role's persona below before executing.")
    lines.append(f"Arguments received: `$ARGUMENTS`")
    lines.append("")
    lines.append(f"Available roles: {', '.join(role_ids)}")
    lines.append("")

    # Include role definitions so the agent has them inline
    for role in all_roles:
        lines.append(f"<details><summary>Role: {role.id}</summary>")
        lines.append("")
        lines.append(role.to_prompt())
        lines.append("")
        lines.append("</details>")
        lines.append("")

    # Include the skill prompt
    lines.append("---")
    lines.append("")
    lines.append(skill.to_prompt())

    return "\n".join(lines)


def sync_claude_skills(project_path: Path, skills: list[Skill],
                       roles: list[Role]) -> list[str]:
    """Write .claude/skills/ entries for each dotai skill with a trigger.

    Returns list of written file paths.
    """
    skills_dir = project_path / ".claude" / "skills"
    written = []

    # Track which skill dirs we're managing so we can clean stale ones
    managed_dirs: set[str] = set()

    for skill in skills:
        if not skill.trigger:
            continue

        cmd_name = skill.trigger.lstrip("/")
        managed_dirs.add(cmd_name)

        skill_dir = skills_dir / cmd_name
        skill_dir.mkdir(parents=True, exist_ok=True)

        skill_md = generate_claude_skill_md(skill, roles)
        skill_path = skill_dir / "SKILL.md"

        # Always overwrite — these are fully managed by dotai
        skill_path.write_text(skill_md)
        written.append(str(skill_path))

    # Clean up stale skill dirs that dotai previously created
    if skills_dir.exists():
        for item in skills_dir.iterdir():
            if item.is_dir() and item.name not in managed_dirs:
                # Only remove if it has our marker comment
                skill_file = item / "SKILL.md"
                if skill_file.exists():
                    content = skill_file.read_text()
                    if "Auto-generated by dotai" in content:
                        shutil.rmtree(item)

    return written


DOTAI_MARKER_START = "<!-- dotai:start -->"
DOTAI_MARKER_END = "<!-- dotai:end -->"


def _merge_with_markers(existing: str, generated: str) -> str:
    """Replace only the dotai-managed section, preserving everything else."""
    block = f"{DOTAI_MARKER_START}\n{generated.strip()}\n{DOTAI_MARKER_END}"

    if DOTAI_MARKER_START in existing:
        # Replace existing managed section
        before = existing.split(DOTAI_MARKER_START)[0].rstrip()
        after_parts = existing.split(DOTAI_MARKER_END, 1)
        after = after_parts[1] if len(after_parts) > 1 else ""
        return before + "\n\n" + block + after.rstrip() + "\n"
    else:
        # First sync — append managed section
        return existing.rstrip() + "\n\n" + block + "\n"


def sync_project(project_path: Path, config: GlobalConfig, project_name: str | None = None, agents: list[str] | None = None) -> list[str]:
    """Write agent bootstrap files into a project directory.

    Preserves any existing local content in the target files. dotai-managed
    content is wrapped in marker comments so re-syncing replaces only the
    managed section.

    Args:
        project_path: Where to write the files
        config: Global config
        project_name: Project name for scoped context
        agents: Which agents to generate for. Default: all.
                Options: "claude", "cursor", "gemini", "generic"

    Returns:
        List of files written
    """
    if agents is None:
        agents = ["claude", "cursor", "gemini", "generic"]

    written = []

    # Pre-load roles and skills once for all generators
    all_roles = load_all_roles(config)
    all_skills = load_all_skills(config)
    if project_name:
        all_roles = [r for r in all_roles if r.scope == project_name or r.scope == "global"]
        all_skills = [s for s in all_skills if s.scope == project_name or s.scope == "global"]

    if "claude" in agents:
        claude_path = project_path / "CLAUDE.md"
        section = generate_claude_md_section(config, project_name, project_path)

        if claude_path.exists():
            existing = claude_path.read_text()
            # Migrate old-style marker to new markers
            if "# AI Context" in existing and DOTAI_MARKER_START not in existing:
                before = existing.split("# AI Context")[0].rstrip()
                claude_path.write_text(before + "\n\n" + DOTAI_MARKER_START + "\n" + section.strip() + "\n" + DOTAI_MARKER_END + "\n")
            else:
                claude_path.write_text(_merge_with_markers(existing, section))
        else:
            claude_path.write_text(DOTAI_MARKER_START + "\n" + section.strip() + "\n" + DOTAI_MARKER_END + "\n")
        written.append(str(claude_path))

        # Generate native Claude Code slash commands from dotai skills
        skill_files = sync_claude_skills(project_path, all_skills, all_roles)
        written.extend(skill_files)

    if "cursor" in agents:
        cursor_path = project_path / ".cursorrules"
        generated = generate_cursorrules(config, project_name, project_path)

        if cursor_path.exists():
            existing = cursor_path.read_text()
            cursor_path.write_text(_merge_with_markers(existing, generated))
        else:
            cursor_path.write_text(DOTAI_MARKER_START + "\n" + generated.strip() + "\n" + DOTAI_MARKER_END + "\n")
        written.append(str(cursor_path))

    if "gemini" in agents:
        gemini_path = project_path / "GEMINI.md"
        generated = generate_gemini_md(config, project_name, project_path)

        if gemini_path.exists():
            existing = gemini_path.read_text()
            gemini_path.write_text(_merge_with_markers(existing, generated))
        else:
            gemini_path.write_text(DOTAI_MARKER_START + "\n" + generated.strip() + "\n" + DOTAI_MARKER_END + "\n")
        written.append(str(gemini_path))

    if "generic" in agents:
        agents_path = project_path / "AGENTS.md"
        generated = generate_agents_md(config, project_name, project_path)

        if agents_path.exists():
            existing = agents_path.read_text()
            agents_path.write_text(_merge_with_markers(existing, generated))
        else:
            agents_path.write_text(DOTAI_MARKER_START + "\n" + generated.strip() + "\n" + DOTAI_MARKER_END + "\n")
        written.append(str(agents_path))

    return written
