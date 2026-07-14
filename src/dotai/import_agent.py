"""Import existing agent bootstrap files into ~/.ai/ knowledge.

Migrates CLAUDE.md, .cursorrules, GEMINI.md, AGENTS.md (and similar)
into freeform rules.md or structured rule files — without LLM magic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .rules import format_rule_markdown
from .utils import generate_id


DOTAI_MARKER_START = "<!-- dotai:start -->"
DOTAI_MARKER_END = "<!-- dotai:end -->"

KNOWN_AGENT_FILES = (
    "CLAUDE.md",
    "AGENTS.md",
    "GEMINI.md",
    ".cursorrules",
    ".cursor/rules",
)


@dataclass
class ImportPlan:
    """What would be written by an import operation."""

    source: Path
    mode: str  # "rules_md" | "rule" | "sections"
    targets: list[tuple[Path, str]] = field(default_factory=list)  # (path, content)
    warnings: list[str] = field(default_factory=list)
    user_content_chars: int = 0


def strip_dotai_managed(content: str) -> str:
    """Remove dotai-managed marker sections; keep user-authored content."""
    if DOTAI_MARKER_START not in content:
        # Also strip legacy "# AI Context" blocks that are pure generated primers
        if "# AI Knowledge Base (~/.ai/)" in content and "This project uses a structured knowledge system" in content:
            # File is mostly generated — try to keep content before the knowledge base header
            if "# AI Knowledge Base" in content:
                before = content.split("# AI Knowledge Base")[0].strip()
                return before
        return content.strip()

    parts: list[str] = []
    rest = content
    while DOTAI_MARKER_START in rest:
        before, _, after = rest.partition(DOTAI_MARKER_START)
        parts.append(before)
        if DOTAI_MARKER_END in after:
            _, _, rest = after.partition(DOTAI_MARKER_END)
        else:
            rest = ""
            break
    parts.append(rest)
    return "\n".join(p.strip() for p in parts if p.strip()).strip()


def split_markdown_sections(content: str) -> list[tuple[str, str]]:
    """Split markdown into (title, body) sections on ## headings.

    Content before the first ## becomes ("_preamble_", body).
    """
    if not content.strip():
        return []

    lines = content.split("\n")
    sections: list[tuple[str, list[str]]] = []
    current_title = "_preamble_"
    current_lines: list[str] = []

    for line in lines:
        if line.startswith("## ") and not line.startswith("### "):
            if current_lines and any(l.strip() for l in current_lines):
                sections.append((current_title, current_lines))
            current_title = line[3:].strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines and any(l.strip() for l in current_lines):
        sections.append((current_title, current_lines))

    return [(title, "\n".join(body).strip()) for title, body in sections if "\n".join(body).strip()]


def plan_import(
    source: Path,
    dest_ai_dir: Path,
    *,
    mode: str = "rules_md",
    rule_name: str | None = None,
    section_min_chars: int = 40,
) -> ImportPlan:
    """Plan an import without writing files.

    Modes:
      - rules_md: append user content as a section in rules.md
      - rule: single structured rule file (requires rule_name or uses source stem)
      - sections: one structured rule per ## section (skips tiny sections)
    """
    source = source.expanduser().resolve()
    plan = ImportPlan(source=source, mode=mode)

    if not source.exists():
        plan.warnings.append(f"File not found: {source}")
        return plan

    if source.is_dir():
        # Import all known agent files from a project directory
        found = False
        rules_md_chunks: list[tuple[str, str]] = []
        for name in KNOWN_AGENT_FILES:
            candidate = source / name
            if candidate.is_file():
                found = True
                if mode == "rules_md":
                    user_content = strip_dotai_managed(candidate.read_text())
                    plan.user_content_chars += len(user_content)
                    if user_content and len(user_content) >= 20:
                        rules_md_chunks.append((candidate.name, user_content))
                    else:
                        plan.warnings.append(
                            f"{candidate.name}: little or no user-authored content after "
                            "removing dotai-managed sections (nothing to import)"
                        )
                    continue
                sub = plan_import(
                    candidate,
                    dest_ai_dir,
                    mode=mode,
                    rule_name=rule_name,
                    section_min_chars=section_min_chars,
                )
                plan.targets.extend(sub.targets)
                plan.warnings.extend(sub.warnings)
                plan.user_content_chars += sub.user_content_chars
        if mode == "rules_md" and rules_md_chunks:
            rules_md = dest_ai_dir / "rules.md"
            merged = rules_md.read_text() if rules_md.exists() else "# Rules\n"
            imported = 0
            for source_name, user_content in rules_md_chunks:
                if user_content in merged:
                    plan.warnings.append(
                        f"{source_name}: content already present in rules.md"
                    )
                    continue
                merged = (
                    merged.rstrip()
                    + f"\n\n## Imported from {source_name}\n\n"
                    + user_content
                    + "\n"
                )
                imported += 1
            if imported:
                plan.targets.append((rules_md, merged))
        if not found:
            plan.warnings.append(
                f"No known agent files ({', '.join(KNOWN_AGENT_FILES)}) in {source}"
            )
        return plan

    raw = source.read_text()
    user_content = strip_dotai_managed(raw)
    plan.user_content_chars = len(user_content)

    if not user_content or len(user_content) < 20:
        plan.warnings.append(
            f"{source.name}: little or no user-authored content after removing "
            "dotai-managed sections (nothing to import)"
        )
        return plan

    if mode == "rules_md":
        rules_md = dest_ai_dir / "rules.md"
        existing = rules_md.read_text() if rules_md.exists() else "# Rules\n"
        header = f"\n\n## Imported from {source.name}\n\n"
        # Avoid double-import of identical blob
        if user_content in existing:
            plan.warnings.append(f"{source.name}: content already present in rules.md")
            return plan
        new_content = existing.rstrip() + header + user_content + "\n"
        plan.targets.append((rules_md, new_content))

    elif mode == "rule":
        name = rule_name or source.stem.replace(".", " ").replace("_", " ").strip()
        if name.startswith("."):
            name = name.lstrip(".")
        if not name:
            name = "imported-conventions"
        rule_id = generate_id(name)
        desc = f"Imported from {source.name}"
        # Prefer first non-empty line as description
        for line in user_content.split("\n"):
            cleaned = re.sub(r"[#*`\[\]]", "", line).strip()
            if cleaned and len(cleaned) > 15:
                desc = cleaned[:120]
                break
        body = user_content
        content = format_rule_markdown(name=name, description=desc, body=body)
        dest = _available_rule_path(dest_ai_dir / "rules", rule_id)
        plan.targets.append((dest, content))

    elif mode == "sections":
        sections = split_markdown_sections(user_content)
        if not sections:
            plan.warnings.append(f"{source.name}: no sections found")
            return plan
        for title, body in sections:
            if len(body) < section_min_chars:
                plan.warnings.append(f"Skipped short section: {title!r} ({len(body)} chars)")
                continue
            if title == "_preamble_":
                name = f"imported-{source.stem}-preamble"
                display = f"Imported preamble from {source.name}"
            else:
                name = title
                display = title
            rule_id = generate_id(name)
            # Avoid collisions within this plan
            dest = _available_rule_path(
                dest_ai_dir / "rules",
                rule_id,
                reserved={p for p, _ in plan.targets},
            )
            content = format_rule_markdown(
                name=display if title != "_preamble_" else name,
                description=f"Imported from {source.name}" + (f" — {title}" if title != "_preamble_" else ""),
                body=body,
            )
            plan.targets.append((dest, content))
        if not plan.targets:
            plan.warnings.append(f"{source.name}: all sections were too short to import")
    else:
        plan.warnings.append(f"Unknown mode: {mode}")

    return plan


def _available_rule_path(
    rules_dir: Path,
    rule_id: str,
    *,
    reserved: set[Path] | None = None,
) -> Path:
    """Return a non-destructive destination for an imported rule."""
    reserved = reserved or set()
    dest = rules_dir / f"{rule_id}.md"
    suffix = 2
    while dest.exists() or dest in reserved:
        dest = rules_dir / f"{rule_id}-{suffix}.md"
        suffix += 1
    return dest


def apply_import_plan(plan: ImportPlan) -> list[Path]:
    """Write planned files. Returns paths written."""
    written: list[Path] = []
    for path, content in plan.targets:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        written.append(path)
    return written
