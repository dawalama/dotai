"""User-level agent adapters for automatic dotai context delivery."""

from __future__ import annotations

import shutil
import shlex
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal


ADAPTER_MARKER_START = "<!-- dotai:agent:claude:start -->"
ADAPTER_MARKER_END = "<!-- dotai:agent:claude:end -->"

CLAUDE_BOOTSTRAP = """# dotai Personal Context

Repository and organization instructions are authoritative. dotai is personal,
supplemental guidance and must never override team instructions.

For substantial coding, debugging, review, planning, verification, or release
work, run this before acting:

`{command} context --agent claude --path . --task "<concise task>" --files "<comma-separated affected files>"`

If affected files are not known yet, omit `--files` only for an initial,
provisional resolution. Discover the relevant files, then you MUST run dotai again
with `--files` before substantive review, editing, or implementation. The second
resolution replaces the provisional one and loads file-scoped rules. Do not call
dotai for casual conversation, simple factual questions, or repeatedly after a
complete file-aware resolution unless the task or affected files materially change.

When the user explicitly invokes a dotai workflow such as `/run_review`, load it
with `{command} context --agent claude --path . --skill run_review`. Treat dotai preferences as soft
taste only; team rules, security constraints, and user instructions take precedence.
"""


@dataclass(frozen=True)
class AgentAdapterPlan:
    """A previewable user-memory change for one supported agent."""

    agent: Literal["claude"]
    path: Path
    action: Literal["create", "update", "remove", "none"]
    content: str | None
    detail: str


def claude_memory_path(home: Path | None = None) -> Path:
    return (home or Path.home()) / ".claude" / "CLAUDE.md"


def _managed_block(command: str) -> str:
    rendered = CLAUDE_BOOTSTRAP.format(command=shlex.quote(command))
    return (
        f"{ADAPTER_MARKER_START}\n"
        f"{rendered.strip()}\n"
        f"{ADAPTER_MARKER_END}"
    )


def _remove_adapter_block(content: str) -> tuple[str, bool]:
    if ADAPTER_MARKER_START not in content or ADAPTER_MARKER_END not in content:
        return content, False
    before, _, rest = content.partition(ADAPTER_MARKER_START)
    _, _, after = rest.partition(ADAPTER_MARKER_END)
    cleaned = "\n\n".join(
        part for part in (before.rstrip(), after.lstrip().rstrip()) if part
    )
    return (cleaned + "\n" if cleaned else ""), True


def plan_claude_setup(
    path: Path | None = None, command: str = "dotai"
) -> AgentAdapterPlan:
    """Plan marker-managed installation without touching Claude user memory."""
    path = path or claude_memory_path()
    block = _managed_block(command)
    if not path.exists():
        return AgentAdapterPlan(
            "claude", path, "create", block + "\n",
            "create user-level Claude memory",
        )
    if path.is_symlink():
        raise ValueError(f"Refusing to modify symlinked Claude memory: {path}")

    existing = path.read_text()
    if (ADAPTER_MARKER_START in existing) != (ADAPTER_MARKER_END in existing):
        raise ValueError(f"Claude memory contains incomplete dotai markers: {path}")
    cleaned, found = _remove_adapter_block(existing)
    content = (
        f"{cleaned.rstrip()}\n\n{block}\n" if cleaned.strip() else block + "\n"
    )
    if found and content == existing:
        return AgentAdapterPlan("claude", path, "none", None, "already configured")
    detail = "refresh dotai block" if found else "append dotai block; preserve existing memory"
    return AgentAdapterPlan("claude", path, "update", content, detail)


def plan_claude_remove(path: Path | None = None) -> AgentAdapterPlan:
    """Plan removal of only dotai's Claude user-memory block."""
    path = path or claude_memory_path()
    if not path.exists():
        return AgentAdapterPlan("claude", path, "none", None, "memory file does not exist")
    if path.is_symlink():
        raise ValueError(f"Refusing to modify symlinked Claude memory: {path}")
    existing = path.read_text()
    if (ADAPTER_MARKER_START in existing) != (ADAPTER_MARKER_END in existing):
        raise ValueError(f"Claude memory contains incomplete dotai markers: {path}")
    cleaned, found = _remove_adapter_block(existing)
    if not found:
        return AgentAdapterPlan("claude", path, "none", None, "dotai block not installed")
    return AgentAdapterPlan(
        "claude", path, "update" if cleaned else "remove",
        cleaned or None, "remove only dotai's managed block",
    )


def claude_adapter_status(path: Path | None = None) -> tuple[str, str]:
    """Return a stable status code and human-readable detail."""
    path = path or claude_memory_path()
    if not path.exists():
        return "not-configured", "Claude user memory does not exist"
    if path.is_symlink():
        return "unsafe", "Claude user memory is a symlink"
    content = path.read_text()
    has_start = ADAPTER_MARKER_START in content
    has_end = ADAPTER_MARKER_END in content
    if has_start and has_end:
        return "configured", "dotai adapter block is installed"
    if has_start or has_end:
        return "invalid", "dotai adapter markers are incomplete"
    return "not-configured", "Claude user memory exists without a dotai block"


def apply_agent_plan(plan: AgentAdapterPlan, backup_root: Path) -> Path | None:
    """Back up existing memory, then apply a reviewed adapter plan."""
    if plan.action == "none":
        return None
    if plan.path.is_symlink():
        raise ValueError(f"Refusing to modify symlinked Claude memory: {plan.path}")

    backup_path: Path | None = None
    if plan.path.exists():
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backup_root.mkdir(parents=True, exist_ok=True)
        backup_path = backup_root / f"CLAUDE-{timestamp}.md"
        shutil.copy2(plan.path, backup_path)

    plan.path.parent.mkdir(parents=True, exist_ok=True)
    if plan.action == "remove":
        plan.path.unlink()
    else:
        plan.path.write_text(plan.content or "")
    return backup_path
