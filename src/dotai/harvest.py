"""Harvest candidate durable rules from native agent auto-memory silos (read-only by default).

Native coding agents (e.g., Claude Code's ~/.claude/projects/<hash>/memory/) accumulate
auto-memory notes silently per tool. Harvesting lets a developer inspect those local notes,
filter out index links and duplicates, and explicitly promote durable lessons into ~/.ai/rules/.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path

from .maintenance import _tokens
from .models import GlobalConfig
from .rules import load_rules_from_dir
from .utils import generate_id

SUPPORTED_HARVEST_SOURCES = ("claude",)

_INDEX_LINK_RE = re.compile(r"^\s*[-*]\s*\[[^\]]+\]\([^)]+\)")


def _parse_frontmatter(raw: str) -> tuple[dict[str, str], str]:
    fm: dict[str, str] = {}
    body = raw
    if raw.startswith("---"):
        parts = raw.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    fm[k.strip().lower()] = v.strip().strip("'\"")
            body = parts[2].strip()
    return fm, body


@dataclass(frozen=True)
class HarvestCandidate:
    """One candidate lesson discovered in a native agent's auto-memory."""

    source: str
    source_path: str
    project_hint: str
    title: str
    body: str
    memory_type: str = "note"
    already_in_dotai: bool = False
    suggested_rule_id: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _jaccard_text(left: str, right: str) -> float:
    lt = set(_tokens(left))
    rt = set(_tokens(right))
    if len(lt) < 4 or len(rt) < 4:
        return 0.0
    return len(lt & rt) / len(lt | rt)


def _is_covered_by_existing(title: str, body: str, existing_texts: list[str]) -> bool:
    combined = f"{title} {body}"
    norm = " ".join(_tokens(combined))
    if not norm:
        return False
    for existing in existing_texts:
        if not existing:
            continue
        if norm in existing or existing in norm:
            return True
        if _jaccard_text(combined, existing) >= 0.65:
            return True
    return False


def _project_hint_from_dir(project_dir_name: str) -> str:
    # Claude Code encodes paths like `-Users-dawa-my-app`
    cleaned = project_dir_name.strip("-")
    parts = [p for p in cleaned.split("-") if p]
    return parts[-1] if parts else project_dir_name


def _extract_from_memory_file(
    path: Path,
    project_hint: str,
    existing_texts: list[str],
) -> list[HarvestCandidate]:
    try:
        raw = path.read_text()
    except OSError:
        return []

    fm, body = _parse_frontmatter(raw)
    candidates: list[HarvestCandidate] = []

    # Structured Claude memory file with YAML frontmatter (name/description/type)
    if fm and (fm.get("name") or fm.get("description") or fm.get("type")):
        mem_type = str(fm.get("type", "note")).strip().lower()
        title = str(fm.get("name") or fm.get("description") or path.stem).strip()
        text = body.strip() or str(fm.get("description") or "").strip()
        if len(text) >= 15:
            candidates.append(HarvestCandidate(
                source="claude",
                source_path=str(path),
                project_hint=project_hint,
                title=title,
                body=text,
                memory_type=mem_type,
                already_in_dotai=_is_covered_by_existing(title, text, existing_texts),
                suggested_rule_id=generate_id(title) or generate_id(path.stem),
            ))
        return candidates

    # Unstructured MEMORY.md or markdown notes: extract substantive bullets (skip index links)
    current_heading = path.stem
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        heading_match = re.match(r"^#{1,4}\s+(.+)$", stripped)
        if heading_match:
            current_heading = heading_match.group(1).strip()
            continue
        if _INDEX_LINK_RE.match(stripped):
            continue
        bullet_match = re.match(r"^[-*]\s+(.+)$", stripped)
        if not bullet_match:
            continue
        item = bullet_match.group(1).strip()
        if len(item) < 20:
            continue
        # Derive a concise title from the first ~6 words
        words = re.findall(r"[A-Za-z0-9_.-]+", item)[:6]
        title = f"{current_heading}: {' '.join(words)}" if current_heading.lower() != "memory" else " ".join(words)
        candidates.append(HarvestCandidate(
            source="claude",
            source_path=str(path),
            project_hint=project_hint,
            title=title,
            body=item,
            memory_type="bullet",
            already_in_dotai=_is_covered_by_existing(title, item, existing_texts),
            suggested_rule_id=generate_id(" ".join(words)) or "harvested-rule",
        ))
    return candidates


def harvest_claude_memory(
    config: GlobalConfig,
    *,
    home: Path | None = None,
    project_filter: str | None = None,
    include_existing: bool = False,
) -> list[HarvestCandidate]:
    """Scan ~/.claude/projects/*/memory/*.md and return candidate durable rules."""
    home = (home or Path.home()).expanduser().resolve()
    projects_root = home / ".claude" / "projects"
    if not projects_root.is_dir():
        return []

    existing_rules = load_rules_from_dir(config.global_rules_path, "global")
    existing_texts = [
        text
        for r in existing_rules
        if (text := " ".join(_tokens(f"{r.name} {r.description} {r.body}")))
    ]

    candidates: list[HarvestCandidate] = []
    for project_dir in sorted(projects_root.iterdir()):
        if not project_dir.is_dir() or project_dir.is_symlink():
            continue
        if project_filter and project_filter.lower() not in project_dir.name.lower():
            continue
        memory_dir = project_dir / "memory"
        if not memory_dir.is_dir() or memory_dir.is_symlink():
            continue
        hint = _project_hint_from_dir(project_dir.name)
        for md_file in sorted(memory_dir.glob("*.md")):
            if not md_file.is_file() or md_file.is_symlink():
                continue
            for item in _extract_from_memory_file(md_file, hint, existing_texts):
                if include_existing or not item.already_in_dotai:
                    candidates.append(item)

    return candidates
