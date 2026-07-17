"""Generate compact, repository-safe local context from ~/.ai/ knowledge."""

import hashlib
import json
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from .models import GlobalConfig, Role, Skill
from .preferences import format_preferences_section, resolve_preference_packs
from .roles import load_all_roles
from .rules import load_rules_from_dir, load_rules_md, resolve_rules_for_project
from .skills import load_all_skills

SyncMode = Literal["local"]


@dataclass(frozen=True)
class SyncPlan:
    """Resolved sync behavior before any files are written."""

    mode: SyncMode
    project_path: Path
    target_path: Path
    git_root: Path | None
    agents: list[str]

TEAM_INSTRUCTION_FILES = {
    "claude": "CLAUDE.md",
    "cursor": ".cursorrules",
    "gemini": "GEMINI.md",
    "generic": "AGENTS.md",
}


def find_git_root(project_path: Path) -> Path | None:
    """Return the containing Git root without inspecting remotes or changing state."""
    try:
        result = subprocess.run(
            ["git", "-C", str(project_path), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return None
    if result.returncode != 0:
        return None
    return Path(result.stdout.strip()).resolve()


def local_context_dir(project_path: Path, config_dir: Path) -> Path:
    """Return a stable, user-local cache path for a repository context."""
    identity = str(project_path.resolve()).encode()
    repo_id = f"{project_path.name}-{hashlib.sha256(identity).hexdigest()[:12]}"
    return config_dir / "contexts" / repo_id


def plan_sync(project_path: Path, config_dir: Path) -> SyncPlan:
    """Plan a repository-safe local context sync without writing anything."""
    project_path = project_path.resolve()
    git_root = find_git_root(project_path)
    target = local_context_dir(git_root or project_path, config_dir)
    return SyncPlan("local", project_path, target, git_root, list(TEAM_INSTRUCTION_FILES))


def _without_dotai_section(text: str) -> str:
    """Remove an existing generated block before treating a file as team guidance."""
    cleaned, _ = _remove_dotai_sections(text)
    return cleaned.strip()


def _remove_dotai_sections(text: str) -> tuple[str, int]:
    """Remove all complete marker blocks while preserving surrounding content."""
    rest = text
    parts: list[str] = []
    removed = 0
    while DOTAI_MARKER_START in rest:
        before, _, after_start = rest.partition(DOTAI_MARKER_START)
        if DOTAI_MARKER_END not in after_start:
            break
        _, _, after = after_start.partition(DOTAI_MARKER_END)
        parts.append(before.rstrip())
        rest = after.lstrip("\n")
        removed += 1
    parts.append(rest.rstrip())
    cleaned = "\n\n".join(part for part in parts if part).strip()
    return (cleaned + "\n" if cleaned else ""), removed


def _local_agent_context(agent: str, primer: str, team_root: Path) -> str:
    """Compose team-owned guidance ahead of subordinate personal context."""
    instruction_file = TEAM_INSTRUCTION_FILES[agent]
    source = team_root / instruction_file
    team_text = _without_dotai_section(source.read_text()) if source.exists() else ""
    lines = [
        "# dotai Local Context",
        "",
        "This context is stored outside the repository and does not modify team files.",
        "Repository and organization instructions are authoritative. Personal dotai rules and",
        "preferences are supplemental: ignore any personal instruction that conflicts with team",
        "guidance, and ask the user when the conflict cannot be resolved safely.",
        "",
    ]
    if team_text:
        lines.extend([
            f"## Team Instructions ({instruction_file}) — Authoritative",
            "",
            team_text,
            "",
        ])
    lines.extend(["## Personal dotai Context — Supplemental", "", primer, ""])
    return "\n".join(lines)


def generate_primer(config: GlobalConfig, project_name: str | None = None,
                    project_path: Path | None = None,
                    compact: bool = False,
                    full: bool = False,
                    extra_prefs: list[str] | None = None) -> str:
    """Generate a portable engineering-judgment primer for any coding agent.

    This is the core knowledge block — it tells the agent what ~/.ai/ is,
    what's available, and how to use it. When project_path is given, also
    discovers local rules in <project>/.ai/rules/.

    Modes:
      - default: full rule bodies + freeform rules.md + active prefs; roles/skills as catalogs
      - compact=True: summaries + file pointers (agents that can read files)
      - full=True: inline full role personas and skill definitions (legacy dump)
      - extra_prefs: session overlay pack ids (on top of project/global active)
    """
    ai_dir = config.global_ai_dir
    roles = load_all_roles(config)
    rules = resolve_rules_for_project(config, project_name)
    skills = load_all_skills(config)
    pref_packs = resolve_preference_packs(
        config, project_name, project_path, extra=extra_prefs
    )

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

    # Freeform rules.md (global + project) — was previously only referenced, never inlined
    freeform_sections: list[tuple[str, str, Path]] = []
    global_rules_md = load_rules_md(ai_dir)
    if global_rules_md:
        freeform_sections.append(("Global (rules.md)", global_rules_md, ai_dir / "rules.md"))
    if project_path:
        local_md = load_rules_md(project_path / ".ai")
        if local_md:
            freeform_sections.append((
                "Project (.ai/rules.md)", local_md, project_path / ".ai" / "rules.md"
            ))
    elif project_name:
        proj = config.get_project(project_name)
        if proj:
            local_md = load_rules_md(proj.full_ai_path)
            if local_md:
                freeform_sections.append((
                    "Project (.ai/rules.md)", local_md, proj.full_ai_path / "rules.md"
                ))

    lines = [
        "# AI Knowledge Base (~/.ai/)",
        "",
        "This project uses dotai to carry the developer's engineering judgment across",
        "coding agents. Load only the rules, preferences, roles, and workflows relevant",
        "to the current task. Project-level overrides live in `.ai/`.",
        "",
        "## Structure",
        "",
        "```",
        "~/.ai/",
        "  rules.md          # Freeform conventions and notes",
        "  rules/            # Structured rules (individual files) — HARD constraints",
        "  preferences/      # Soft taste packs (borrowable style priors)",
        "  roles/            # Cognitive modes (personas for different tasks)",
        "  skills/           # Reusable workflows (slash commands)",
        "  tools/            # Python tool implementations",
        "```",
        "",
        "Project-specific overrides live in `<project>/.ai/` with the same structure.",
        "",
        "**Team boundary:** repository and organization instructions outside dotai are authoritative.",
        "Treat personal dotai rules and preferences as supplemental. If they conflict with team guidance,",
        "follow the team guidance and ask the user when the conflict is ambiguous.",
        "",
        "**Precedence:** hard rules > freeform rules.md > active preference packs > model default.",
        "Preference packs are soft taste (stack, structure, micro-style). Never override security/architecture rules.",
        "",
    ]

    # Freeform conventions (rules.md) — high value, previously missing from primer
    if freeform_sections:
        lines.append("## Freeform Conventions (rules.md)")
        lines.append("")
        if compact and not full:
            lines.append("Load these notes on demand when their scope is relevant.")
        else:
            lines.append("Follow these project/global notes in addition to structured rules.")
        lines.append("")
        for label, body, source_path in freeform_sections:
            if compact and not full:
                lines.append(f"- **{label}** — `{source_path}`")
            else:
                lines.append(f"### {label}")
                lines.append("")
                lines.append(body)
                lines.append("")
        lines.append("")

    # Structured rules — always high priority
    if project_rules:
        lines.append("## Active Rules")
        lines.append("")
        if compact and not full:
            # Summary table with file pointers — agent reads full rule on demand
            for rule in project_rules:
                globs = f" (applies to: `{', '.join(rule.globs)}`)" if rule.globs else ""
                lines.append(f"- **{rule.name}**: {rule.description}{globs}")
            lines.append("")
            lines.append("Read each rule file fully before acting in matching paths.")
            lines.append("")
        else:
            # Full inline content (default for agents that may not read external files)
            for rule in project_rules:
                lines.append(rule.to_prompt())
                lines.append("")
        lines.append("")

    # Active preference / taste packs (soft priors — after hard rules)
    pref_section = format_preferences_section(
        pref_packs, compact=compact and not full
    )
    if pref_section:
        lines.append(pref_section)
        lines.append("")

    # Roles — catalog by default; full personas only with full=True
    if project_roles:
        lines.append("## Available Roles")
        lines.append("")
        for role in project_roles:
            scope_tag = f" [{role.scope}]" if role.scope != "global" else ""
            path_hint = (
                f" — `{role.file_path}`"
                if role.file_path and compact and not full
                else ""
            )
            lines.append(f"- **{role.name}**{scope_tag}: {role.description}{path_hint}")
        lines.append("")

        if full and not compact:
            lines.append("To adopt a role, follow its persona below.")
            lines.append("")
            for role in project_roles:
                lines.append(f"### Role: {role.name}")
                lines.append("")
                lines.append(role.to_prompt())
                lines.append("")
        else:
            lines.append(
                "To adopt a role, read its file from `~/.ai/roles/` (or project `.ai/roles/`) "
                "and follow its persona. Use `dotai context --role <name>` to resolve it."
            )
            lines.append("")

    # Skills — catalog by default (avoids dumping every workflow into AGENTS.md)
    if project_skills:
        lines.append("## Available Skills")
        lines.append("")

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
                detail = "" if compact and not full else f": {skill.description[:80]}"
                lines.append(f"- **{skill.name}**{trigger}{role_ref}{ctx}{detail}")
            lines.append("")

        if uncategorized:
            for skill in uncategorized:
                trigger = f" `{skill.trigger}`" if skill.trigger else ""
                role_ref = f" (role: {skill.role})" if skill.role else ""
                detail = "" if compact and not full else f": {skill.description[:80]}"
                lines.append(f"- **{skill.name}**{trigger}{role_ref}{detail}")
            lines.append("")

        lines.append(
            "Load a full skill only when selected with `dotai context --path . --skill <id>` "
            "through an agent adapter. Folder skills may include helper scripts in `scripts/`."
        )
        lines.append("")

        if full:
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
        "1. **Start of session**: Keep universal rule summaries and the team-authority boundary active",
        "2. **Before a task**: Run `dotai context --path . --files <paths>` and load a skill only when selected",
        "3. **Teach judgment**: Use `dotai learn --directive` for standards and taste; capture corrections when needed",
        "4. **Borrow style**: Preference packs (`dotai prefs use`) are soft taste — never override hard rules",
        "5. **When unsure**: Structured rules > freeform notes > preference packs; project overrides global",
        "",
    ])

    if not compact or full:
        lines.extend([
            "## Composing Skills with Roles",
            "",
            "When the user writes `/<skill> as <role>`, adopt that role's full persona",
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
                               project_path: Path | None = None,
                               full: bool = False,
                               extra_prefs: list[str] | None = None) -> str:
    """Generate a section to append to CLAUDE.md.

    Uses compact mode since Claude Code can read files and has native
    slash commands — no need for full inline content (unless full=True).
    """
    primer = generate_primer(
        config, project_name, project_path,
        compact=not full,
        full=full,
        extra_prefs=extra_prefs,
    )
    return f"""
# AI Context

{primer}

Read `~/.ai/rules.md` and structured rules at the start of every conversation.
"""


def generate_cursorrules(config: GlobalConfig, project_name: str | None = None,
                         project_path: Path | None = None,
                         full: bool = False,
                         extra_prefs: list[str] | None = None) -> str:
    """Generate .cursorrules content."""
    return generate_primer(
        config, project_name, project_path, compact=not full,
        full=full, extra_prefs=extra_prefs
    )


def generate_gemini_md(config: GlobalConfig, project_name: str | None = None,
                       project_path: Path | None = None,
                       full: bool = False,
                       extra_prefs: list[str] | None = None) -> str:
    """Generate GEMINI.md for Gemini CLI.

    Gemini CLI discovers GEMINI.md files in the project root and
    concatenates them into context. It also reads ~/.gemini/GEMINI.md
    for global instructions.
    """
    primer = generate_primer(
        config, project_name, project_path, compact=not full,
        full=full, extra_prefs=extra_prefs
    )
    return f"""# Project Context

{primer}

This file is auto-generated by dotai. Do not edit manually.
Run `dotai sync` to regenerate.
"""


def generate_agents_md(config: GlobalConfig, project_name: str | None = None,
                       project_path: Path | None = None,
                       full: bool = False,
                       extra_prefs: list[str] | None = None) -> str:
    """Generate AGENTS.md (generic agent bootstrap)."""
    primer = generate_primer(
        config, project_name, project_path, compact=not full,
        full=full, extra_prefs=extra_prefs
    )
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


def sync_project(project_path: Path, config: GlobalConfig, project_name: str | None = None,
                 agents: list[str] | None = None, full: bool = False,
                 extra_prefs: list[str] | None = None) -> list[str]:
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
        full: When True, inline complete rules, roles, skills, and preferences.
              The default is a compact bootstrap with summaries and pointers.
        extra_prefs: Session overlay preference pack ids.

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
        section = generate_claude_md_section(
            config, project_name, project_path, full=full, extra_prefs=extra_prefs
        )

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
        generated = generate_cursorrules(
            config, project_name, project_path, full=full, extra_prefs=extra_prefs
        )

        if cursor_path.exists():
            existing = cursor_path.read_text()
            cursor_path.write_text(_merge_with_markers(existing, generated))
        else:
            cursor_path.write_text(DOTAI_MARKER_START + "\n" + generated.strip() + "\n" + DOTAI_MARKER_END + "\n")
        written.append(str(cursor_path))

    if "gemini" in agents:
        gemini_path = project_path / "GEMINI.md"
        generated = generate_gemini_md(
            config, project_name, project_path, full=full, extra_prefs=extra_prefs
        )

        if gemini_path.exists():
            existing = gemini_path.read_text()
            gemini_path.write_text(_merge_with_markers(existing, generated))
        else:
            gemini_path.write_text(DOTAI_MARKER_START + "\n" + generated.strip() + "\n" + DOTAI_MARKER_END + "\n")
        written.append(str(gemini_path))

    if "generic" in agents:
        agents_path = project_path / "AGENTS.md"
        generated = generate_agents_md(
            config, project_name, project_path, full=full, extra_prefs=extra_prefs
        )

        if agents_path.exists():
            existing = agents_path.read_text()
            agents_path.write_text(_merge_with_markers(existing, generated))
        else:
            agents_path.write_text(DOTAI_MARKER_START + "\n" + generated.strip() + "\n" + DOTAI_MARKER_END + "\n")
        written.append(str(agents_path))

    return written


def sync_local_context(plan: SyncPlan, config: GlobalConfig,
                       project_name: str | None = None) -> list[str]:
    """Generate context outside the repository, preserving team-owned files."""
    if plan.mode != "local":
        raise ValueError("sync_local_context requires a local sync plan")

    plan.target_path.mkdir(parents=True, exist_ok=True)
    primer = generate_primer(
        config, project_name, plan.project_path,
        compact=True,
    )
    written: list[str] = []
    generated: dict[str, str] = {}
    team_root = plan.git_root or plan.project_path
    for agent in plan.agents:
        if agent not in TEAM_INSTRUCTION_FILES:
            raise ValueError(f"Unknown agent: {agent}")
        filename = TEAM_INSTRUCTION_FILES[agent]
        target = plan.target_path / filename
        target.write_text(_local_agent_context(agent, primer, team_root))
        written.append(str(target))
        generated[agent] = filename

    manifest = plan.target_path / "manifest.json"
    manifest.write_text(json.dumps({
        "mode": plan.mode,
        "project_path": str(plan.project_path),
        "git_root": str(plan.git_root) if plan.git_root else None,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "files": generated,
        "precedence": ["team", "personal-dotai", "model-default"],
    }, indent=2) + "\n")
    written.append(str(manifest))
    return written
