"""Deterministic local insights derived from resolution receipt metadata."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from .models import GlobalConfig
from .preferences import load_all_preferences
from .roles import load_all_roles
from .rules import load_all_rules
from .skills import load_all_skills


@dataclass(frozen=True)
class ItemInsight:
    kind: str
    item_id: str
    selected: int = 0
    exposed: int = 0
    last_selected: str | None = None

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "item_id": self.item_id,
            "selected": self.selected,
            "exposed": self.exposed,
            "last_selected": self.last_selected,
        }


@dataclass(frozen=True)
class InsightsReport:
    resolutions: int
    complete: int
    provisional: int
    first_resolution: str | None
    last_resolution: str | None
    agents: list[str]
    projects: list[str]
    items: list[ItemInsight]
    unused: dict[str, list[str]]

    def to_dict(self) -> dict:
        return {
            "resolutions": self.resolutions,
            "complete": self.complete,
            "provisional": self.provisional,
            "first_resolution": self.first_resolution,
            "last_resolution": self.last_resolution,
            "agents": self.agents,
            "projects": self.projects,
            "items": [item.to_dict() for item in self.items],
            "unused": self.unused,
        }


def load_receipt_history(
    receipts_dir: Path,
    agent: str | None = None,
    project_path: Path | None = None,
) -> list[dict]:
    """Load valid metadata receipts without following symlinks."""
    if agent and not re.fullmatch(r"[a-z0-9-]+", agent):
        raise ValueError(f"Invalid agent receipt id: {agent}")
    history_root = receipts_dir / "history"
    receipts: list[dict] = []
    if history_root.is_dir() and not history_root.is_symlink():
        agent_dirs = [history_root / agent] if agent else sorted(history_root.iterdir())
        for agent_dir in agent_dirs:
            if not agent_dir.is_dir() or agent_dir.is_symlink():
                continue
            for path in agent_dir.glob("*.json"):
                if not path.is_file() or path.is_symlink():
                    continue
                try:
                    payload = json.loads(path.read_text())
                except (OSError, json.JSONDecodeError):
                    continue
                if isinstance(payload, dict):
                    receipts.append(payload)

    # Upgrade path: before history existed, each agent had one latest receipt.
    # Merge those files and de-duplicate the latest event already in history.
    if receipts_dir.is_dir() and not receipts_dir.is_symlink():
        latest = [receipts_dir / f"{agent}.json"] if agent else receipts_dir.glob("*.json")
        for path in latest:
            if not path.is_file() or path.is_symlink():
                continue
            try:
                payload = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict):
                receipts.append(payload)

    unique: dict[str, dict] = {}
    for receipt in receipts:
        key = json.dumps(receipt, sort_keys=True)
        unique[key] = receipt
    receipts = list(unique.values())

    if agent:
        receipts = [receipt for receipt in receipts if receipt.get("agent") == agent]
    if project_path:
        expected = str(project_path.resolve())
        receipts = [receipt for receipt in receipts if receipt.get("project_path") == expected]
    return sorted(receipts, key=lambda receipt: str(receipt.get("resolved_at", "")))


def build_insights(
    config: GlobalConfig,
    receipts_dir: Path,
    agent: str | None = None,
    project_path: Path | None = None,
) -> InsightsReport:
    """Aggregate factual usage signals from local receipt metadata."""
    receipts = load_receipt_history(receipts_dir, agent, project_path)
    selected: dict[tuple[str, str], int] = defaultdict(int)
    exposed: dict[tuple[str, str], int] = defaultdict(int)
    last_selected: dict[tuple[str, str], str] = {}

    for receipt in receipts:
        resolved_at = str(receipt.get("resolved_at", ""))
        for rule_id in receipt.get("universal_rules") or []:
            if isinstance(rule_id, str):
                exposed[("rule", rule_id)] += 1
        groups = {
            "rule": receipt.get("expanded_rules") or [],
            "preference": receipt.get("preferences") or [],
            "skill": [receipt.get("skill")] if receipt.get("skill") else [],
            "role": [receipt.get("role")] if receipt.get("role") else [],
        }
        for kind, ids in groups.items():
            for item_id in ids:
                if not isinstance(item_id, str):
                    continue
                key = (kind, item_id)
                selected[key] += 1
                if resolved_at >= last_selected.get(key, ""):
                    last_selected[key] = resolved_at

    project_name = next(
        (
            project.name
            for project in config.projects
            if project_path and project.path.resolve() == project_path.resolve()
        ),
        None,
    )

    def in_scope(item) -> bool:
        return not project_name or item.scope in {"global", project_name}
    known = {
        "rule": {item.id for item in load_all_rules(config) if item.enabled and in_scope(item)},
        "preference": {
            item.id for item in load_all_preferences(config) if item.enabled and in_scope(item)
        },
        "role": {item.id for item in load_all_roles(config) if in_scope(item)},
        "skill": {item.id for item in load_all_skills(config) if in_scope(item)},
    }
    keys = set(selected) | set(exposed)
    items = [
        ItemInsight(
            kind=kind,
            item_id=item_id,
            selected=selected[(kind, item_id)],
            exposed=exposed[(kind, item_id)],
            last_selected=last_selected.get((kind, item_id)),
        )
        for kind, item_id in sorted(
            keys, key=lambda key: (-selected[key], -exposed[key], key[0], key[1])
        )
    ]
    unused = {
        kind: sorted(item_ids - {item_id for item_kind, item_id in selected if item_kind == kind})
        for kind, item_ids in known.items()
    }
    times = [str(receipt.get("resolved_at")) for receipt in receipts if receipt.get("resolved_at")]
    return InsightsReport(
        resolutions=len(receipts),
        complete=sum(not bool(receipt.get("provisional")) for receipt in receipts),
        provisional=sum(bool(receipt.get("provisional")) for receipt in receipts),
        first_resolution=min(times) if times else None,
        last_resolution=max(times) if times else None,
        agents=sorted({str(receipt.get("agent")) for receipt in receipts if receipt.get("agent")}),
        projects=sorted({str(receipt.get("project_path")) for receipt in receipts if receipt.get("project_path")}),
        items=items,
        unused=unused,
    )
