"""Deterministic auditing and conservative compression for dotai rules."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .models import GlobalConfig, Rule
from .rules import load_rules_from_dir, resolve_rules_for_project


SEVERITY_ORDER = {"info": 0, "low": 1, "medium": 2, "high": 3}
GENERIC_RULES = {
    "write clean code",
    "use clear variable names",
    "write good code",
    "follow best practices",
    "be careful",
    "keep code simple",
    "add comments",
}
PREFERENCE_MARKERS = (
    "prefer ",
    "we like ",
    "usually use ",
    "when possible",
    "style choice",
)
HIGH_CONSEQUENCE_MARKERS = (
    "credential",
    "secret",
    "password",
    "token",
    "authorization",
    "security",
    "production data",
    "delete",
    "destructive",
)
STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "do", "for", "from",
    "in", "is", "it", "of", "on", "or", "that", "the", "this", "to", "use",
    "when", "with",
}


@dataclass(frozen=True)
class AuditFinding:
    code: str
    severity: str
    rule_ids: list[str]
    message: str
    suggestion: str
    evidence: str = ""


@dataclass(frozen=True)
class CompressionAction:
    action: str
    rule_ids: list[str]
    message: str
    estimated_tokens_saved: int = 0
    estimated_tokens_saved_low: int = 0
    estimated_tokens_saved_high: int = 0
    paths_to_remove: list[str] = field(default_factory=list)
    source_path: str = ""
    original_sha256: str = ""
    automatic: bool = False


@dataclass
class AuditReport:
    scope: str
    rule_count: int
    estimated_tokens: int
    findings: list[AuditFinding]
    rule_metrics: list["RuleMetric"] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CompressionPlan:
    scope: str
    rule_count: int
    estimated_tokens_before: int
    estimated_tokens_after: int
    actions: list[CompressionAction]

    @property
    def automatic_actions(self) -> list[CompressionAction]:
        return [action for action in self.actions if action.automatic]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class CompressionResult:
    backup_path: Path | None
    removed_paths: list[Path]
    plan: CompressionPlan


@dataclass(frozen=True)
class ProposedRuleChange:
    rule_id: str
    source_path: Path
    original_sha256: str
    content: str


@dataclass(frozen=True)
class CompressionProposal:
    version: int
    scope: str
    changes: list[ProposedRuleChange]


@dataclass(frozen=True)
class RuleMetric:
    rule_id: str
    estimated_tokens: int
    percent_of_total: float
    risk: str
    estimated_savings_low: int = 0
    estimated_savings_high: int = 0
    recent_before_tokens: int = 0
    recent_saved_tokens: int = 0
    recent_compressed_at: str = ""


def estimate_tokens(text: str) -> int:
    """Return a stable, tokenizer-free context estimate."""
    return max(1, math.ceil(len(text) / 4)) if text else 0


def audit_rules(
    config: GlobalConfig,
    *,
    project_name: str | None = None,
    include_disabled: bool = False,
) -> AuditReport:
    """Audit the effective rule set without modifying files."""
    if project_name:
        rules = resolve_rules_for_project(config, project_name)
        if include_disabled:
            project = config.get_project(project_name)
            if project:
                rules = _dedupe_rule_paths(
                    load_rules_from_dir(config.global_rules_path, "global")
                    + load_rules_from_dir(project.rules_path, project_name)
                )
        scope = project_name
    else:
        rules = load_rules_from_dir(config.global_rules_path, "global")
        if not include_disabled:
            rules = [rule for rule in rules if rule.enabled]
        scope = "global"

    total = sum(estimate_tokens(rule.to_prompt()) for rule in rules)
    history_ai_dir = _scope_ai_dir(config, project_name)
    recent_history = _load_recent_compression(history_ai_dir)
    metrics = [_rule_metric(rule, total, recent_history) for rule in rules]
    metrics.sort(key=lambda metric: (-metric.estimated_tokens, metric.rule_id))
    findings = _structural_findings(rules, metrics)
    findings.extend(_overlap_findings(rules))
    findings.sort(
        key=lambda finding: (
            -SEVERITY_ORDER[finding.severity],
            finding.code,
            finding.rule_ids,
        )
    )
    return AuditReport(scope, len(rules), total, findings, metrics)


def build_compression_plan(
    config: GlobalConfig,
    *,
    project_name: str | None = None,
) -> CompressionPlan:
    """Build a read-only compression plan.

    Only exact duplicates in the same owning scope are automatically removable.
    All semantic or preference-like findings remain review suggestions.
    """
    if project_name:
        project = config.get_project(project_name)
        if not project:
            raise ValueError(f"Project '{project_name}' not found")
        rules = [rule for rule in load_rules_from_dir(project.rules_path, project_name) if rule.enabled]
        scope = project_name
    else:
        rules = [rule for rule in load_rules_from_dir(config.global_rules_path, "global") if rule.enabled]
        scope = "global"

    actions: list[CompressionAction] = []
    exact_groups = _exact_duplicate_groups(rules)
    automatic_ids: set[str] = set()
    saved = 0
    for group in exact_groups:
        canonical, *duplicates = sorted(group, key=_rule_sort_key)
        removed_tokens = sum(estimate_tokens(rule.to_prompt()) for rule in duplicates)
        saved += removed_tokens
        automatic_ids.update(rule.id for rule in duplicates)
        actions.append(
            CompressionAction(
                action="remove-exact-duplicate",
                rule_ids=[canonical.id, *[rule.id for rule in duplicates]],
                message=f"Keep '{canonical.id}'; remove {len(duplicates)} exact duplicate(s)",
                estimated_tokens_saved=removed_tokens,
                estimated_tokens_saved_low=removed_tokens,
                estimated_tokens_saved_high=removed_tokens,
                paths_to_remove=[str(rule.file_path) for rule in duplicates if rule.file_path],
                automatic=True,
            )
        )

    local_total = sum(estimate_tokens(rule.to_prompt()) for rule in rules)
    recent_history = _load_recent_compression(_scope_ai_dir(config, project_name))
    local_metrics = [_rule_metric(rule, local_total, recent_history) for rule in rules]
    metrics_by_id = {metric.rule_id: metric for metric in local_metrics}
    local_findings = _structural_findings(rules, local_metrics) + _overlap_findings(rules)
    for finding in local_findings:
        if finding.code == "exact-duplicate":
            continue
        if all(rule_id in automatic_ids for rule_id in finding.rule_ids):
            continue
        if finding.code in {"likely-preference", "generic-guidance", "high-overlap", "large-rule"}:
            metric = metrics_by_id.get(finding.rule_ids[0])
            actions.append(
                CompressionAction(
                    action={
                        "likely-preference": "review-as-preference",
                        "generic-guidance": "review-for-archive",
                        "high-overlap": "review-for-merge",
                        "large-rule": "review-for-trimming",
                    }[finding.code],
                    rule_ids=finding.rule_ids,
                    message=finding.suggestion,
                    estimated_tokens_saved_low=metric.estimated_savings_low if metric else 0,
                    estimated_tokens_saved_high=metric.estimated_savings_high if metric else 0,
                    source_path=(
                        str(next((rule.file_path for rule in rules if rule.id == finding.rule_ids[0]), ""))
                        if len(finding.rule_ids) == 1
                        else ""
                    ),
                    original_sha256=(
                        _file_sha256(next(
                            rule.file_path for rule in rules
                            if rule.id == finding.rule_ids[0] and rule.file_path
                        ))
                        if len(finding.rule_ids) == 1
                        and any(rule.id == finding.rule_ids[0] and rule.file_path for rule in rules)
                        else ""
                    ),
                )
            )

    actions.sort(key=lambda action: (not action.automatic, action.action, action.rule_ids))
    before = sum(estimate_tokens(rule.to_prompt()) for rule in rules)
    return CompressionPlan(scope, len(rules), before, max(0, before - saved), actions)


def apply_compression_plan(
    config: GlobalConfig,
    plan: CompressionPlan,
    *,
    project_name: str | None = None,
) -> CompressionResult:
    """Apply safe automatic actions after staging, validation, and backup."""
    if plan.scope != (project_name or "global"):
        raise ValueError("Compression plan scope does not match apply scope")
    removable = [Path(path) for action in plan.automatic_actions for path in action.paths_to_remove]
    if not removable:
        return CompressionResult(None, [], plan)

    ai_dir = _scope_ai_dir(config, project_name)
    rules_dir = ai_dir / "rules"
    for path in removable:
        if path.parent.resolve() != rules_dir.resolve() or not path.is_file():
            raise ValueError(f"Unsafe or missing compression path: {path}")

    with tempfile.TemporaryDirectory(prefix="dotai-compress-", dir=ai_dir.parent) as tmp:
        staged_rules = Path(tmp) / "rules"
        shutil.copytree(rules_dir, staged_rules)
        for path in removable:
            (staged_rules / path.name).unlink()
        staged = load_rules_from_dir(staged_rules, plan.scope)
        if len(staged) != len(list(staged_rules.glob("*.md"))):
            raise ValueError("Staged rule validation failed")
        if _exact_duplicate_groups(staged):
            raise ValueError("Staged rules still contain exact duplicates")

        backup_path = _create_backup(ai_dir, plan, removable)
        removed: list[Path] = []
        for path in removable:
            path.unlink()
            removed.append(path)

    finalize_compression_backup(
        config,
        backup_path,
        project_name=project_name,
    )
    return CompressionResult(backup_path, removed, plan)


def create_compression_backup(
    config: GlobalConfig,
    plan: CompressionPlan,
    *,
    project_name: str | None = None,
) -> Path:
    """Create the mandatory snapshot used by an interactive compression session."""
    if plan.scope != (project_name or "global"):
        raise ValueError("Compression plan scope does not match backup scope")
    ai_dir = _scope_ai_dir(config, project_name)
    return _create_backup(ai_dir, plan, [])


def finalize_compression_backup(
    config: GlobalConfig,
    backup_path: Path,
    *,
    project_name: str | None = None,
) -> dict:
    """Record actual post-apply hashes and token savings in a backup manifest."""
    ai_dir = _scope_ai_dir(config, project_name)
    backup = backup_path.resolve()
    manifest_path = backup / "manifest.json"
    if backup.parent != (ai_dir / "backups").resolve() or not manifest_path.is_file():
        raise ValueError("Invalid compression backup path")

    manifest = json.loads(manifest_path.read_text())
    scope = project_name or "global"
    before_rules = load_rules_from_dir(backup / "rules", scope)
    after_rules = load_rules_from_dir(ai_dir / "rules", scope)
    before_by_file = {rule.file_path.name: rule for rule in before_rules if rule.file_path}
    after_by_file = {rule.file_path.name: rule for rule in after_rules if rule.file_path}
    changes = []
    for filename in sorted(set(before_by_file) | set(after_by_file)):
        before = before_by_file.get(filename)
        after = after_by_file.get(filename)
        before_sha = _file_sha256(before.file_path) if before and before.file_path else ""
        after_sha = _file_sha256(after.file_path) if after and after.file_path else ""
        if before_sha == after_sha:
            continue
        before_tokens = estimate_tokens(before.to_prompt()) if before and before.enabled else 0
        after_tokens = estimate_tokens(after.to_prompt()) if after and after.enabled else 0
        changes.append({
            "rule_id": (after or before).id,
            "path": f"rules/{filename}",
            "before_sha256": before_sha,
            "after_sha256": after_sha,
            "before_tokens": before_tokens,
            "after_tokens": after_tokens,
            "saved_tokens": max(0, before_tokens - after_tokens),
        })

    before_total = sum(
        estimate_tokens(rule.to_prompt()) for rule in before_rules if rule.enabled
    )
    after_total = sum(
        estimate_tokens(rule.to_prompt()) for rule in after_rules if rule.enabled
    )
    completed_at = datetime.now(timezone.utc).isoformat()
    manifest.update({
        "status": "complete",
        "completed_at": completed_at,
        "actual_tokens_before": before_total,
        "actual_tokens_after": after_total,
        "actual_tokens_saved": max(0, before_total - after_total),
        "changes": changes,
    })
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def load_compression_proposal(
    proposal_path: Path,
    config: GlobalConfig,
    *,
    project_name: str | None = None,
) -> CompressionProposal:
    """Load and fully validate a versioned agent-generated proposal."""
    try:
        data = json.loads(proposal_path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Could not read compression proposal: {error}") from error
    if not isinstance(data, dict) or data.get("version") != 1:
        raise ValueError("Compression proposal must use schema version 1")
    expected_scope = project_name or "global"
    if data.get("scope") != expected_scope:
        raise ValueError(
            f"Proposal scope '{data.get('scope')}' does not match '{expected_scope}'"
        )
    raw_changes = data.get("changes")
    if not isinstance(raw_changes, list) or not raw_changes:
        raise ValueError("Compression proposal must contain at least one change")

    ai_dir = _scope_ai_dir(config, project_name)
    rules_dir = (ai_dir / "rules").resolve()
    seen: set[str] = set()
    changes: list[ProposedRuleChange] = []
    for raw in raw_changes:
        if not isinstance(raw, dict):
            raise ValueError("Each proposal change must be an object")
        rule_id = str(raw.get("rule_id", "")).strip()
        source_path = Path(str(raw.get("source_path", ""))).expanduser().resolve()
        original_sha256 = str(raw.get("original_sha256", "")).strip()
        content = raw.get("content")
        if not rule_id or rule_id in seen:
            raise ValueError(f"Duplicate or missing rule_id: {rule_id!r}")
        if source_path.parent != rules_dir or not source_path.is_file():
            raise ValueError(f"Unsafe or missing proposal source path: {source_path}")
        if not isinstance(content, str) or not content.strip():
            raise ValueError(f"Proposal content is empty for '{rule_id}'")
        if _file_sha256(source_path) != original_sha256:
            raise ValueError(
                f"Rule '{rule_id}' changed after the proposal was generated; regenerate it"
            )
        original_rule = next(
            (
                rule for rule in load_rules_from_dir(rules_dir, expected_scope)
                if rule.file_path and rule.file_path.resolve() == source_path
            ),
            None,
        )
        if not original_rule or original_rule.id != rule_id:
            raise ValueError(f"Proposal identity does not match source rule '{rule_id}'")
        with tempfile.TemporaryDirectory(prefix="dotai-proposal-validate-") as tmp:
            staged = Path(tmp) / source_path.name
            staged.write_text(content)
            parsed = load_rules_from_dir(Path(tmp), expected_scope)
            if len(parsed) != 1 or parsed[0].id != rule_id:
                raise ValueError(f"Proposed rule '{rule_id}' is invalid or renamed")
        seen.add(rule_id)
        changes.append(ProposedRuleChange(rule_id, source_path, original_sha256, content))
    return CompressionProposal(1, expected_scope, changes)


def write_reviewed_rule(
    config: GlobalConfig,
    *,
    project_name: str | None,
    rule_path: Path,
    content: str,
    backup_path: Path,
    expected_sha256: str | None = None,
) -> None:
    """Atomically write an approved rule edit after validating backup and identity."""
    ai_dir = _scope_ai_dir(config, project_name)
    rules_dir = ai_dir / "rules"
    resolved = rule_path.resolve()
    if resolved.parent != rules_dir.resolve() or not resolved.is_file():
        raise ValueError(f"Unsafe or missing rule path: {rule_path}")
    backups_dir = (ai_dir / "backups").resolve()
    backup_resolved = backup_path.resolve()
    if backup_resolved.parent != backups_dir or not (backup_resolved / "manifest.json").is_file():
        raise ValueError("A valid compression backup is required before writing")
    if expected_sha256 and _file_sha256(rule_path) != expected_sha256:
        raise ValueError("Rule changed after approval; regenerate the compression proposal")

    with tempfile.TemporaryDirectory(prefix="dotai-rule-edit-", dir=rules_dir) as tmp:
        staged = Path(tmp) / rule_path.name
        staged.write_text(content)
        parsed = load_rules_from_dir(Path(tmp), project_name or "global")
        if len(parsed) != 1:
            raise ValueError("Edited rule is not valid structured Markdown")
        original = load_rules_from_dir(rules_dir, project_name or "global")
        original_rule = next(
            (
                rule for rule in original
                if rule.file_path and rule.file_path.resolve() == rule_path.resolve()
            ),
            None,
        )
        if not original_rule or parsed[0].id != original_rule.id:
            raise ValueError("Edited rule must preserve its rule name and identity")
        replacement = rules_dir / f".{rule_path.name}.compressing"
        replacement.write_text(content)
        os.replace(replacement, rule_path)


def remove_reviewed_duplicates(
    config: GlobalConfig,
    *,
    project_name: str | None,
    paths: list[Path],
    backup_path: Path,
) -> list[Path]:
    """Remove approved exact duplicates after validating the session backup."""
    ai_dir = _scope_ai_dir(config, project_name)
    rules_dir = (ai_dir / "rules").resolve()
    backup_resolved = backup_path.resolve()
    if (
        backup_resolved.parent != (ai_dir / "backups").resolve()
        or not (backup_resolved / "manifest.json").is_file()
    ):
        raise ValueError("A valid compression backup is required before removing rules")
    resolved_paths = [path.resolve() for path in paths]
    if any(path.parent != rules_dir or not path.is_file() for path in resolved_paths):
        raise ValueError("Unsafe or missing duplicate rule path")
    for path in resolved_paths:
        path.unlink()
    return resolved_paths


def _rule_metric(
    rule: Rule,
    total_tokens: int,
    recent_history: dict[str, dict] | None = None,
) -> RuleMetric:
    tokens = estimate_tokens(rule.to_prompt())
    combined = f"{rule.name} {rule.description} {rule.body}".lower()
    if any(marker in combined for marker in HIGH_CONSEQUENCE_MARKERS):
        risk = "high"
        low_rate, high_rate = 0.10, 0.20
    elif any(marker in combined for marker in ("never", "always", "must", "required", "ban")):
        risk = "medium"
        low_rate, high_rate = 0.20, 0.35
    else:
        risk = "low"
        low_rate, high_rate = 0.25, 0.40
    if tokens < 500:
        savings_low = savings_high = 0
    else:
        savings_low = max(1, round(tokens * low_rate))
        savings_high = max(savings_low, round(tokens * high_rate))
    recent = (recent_history or {}).get(rule.id, {})
    current_sha = _file_sha256(rule.file_path) if rule.file_path else ""
    if recent.get("after_sha256") != current_sha:
        recent = {}
    return RuleMetric(
        rule_id=rule.id,
        estimated_tokens=tokens,
        percent_of_total=(tokens / total_tokens * 100) if total_tokens else 0,
        risk=risk,
        estimated_savings_low=savings_low,
        estimated_savings_high=savings_high,
        recent_before_tokens=int(recent.get("before_tokens", 0)),
        recent_saved_tokens=int(recent.get("saved_tokens", 0)),
        recent_compressed_at=str(recent.get("completed_at", "")),
    )


def _reviewable_sections(body: str) -> list[str]:
    """Identify prose/example-heavy Markdown sections worth human review."""
    candidates: list[str] = []
    keywords = (
        "example", "pattern", "rationale", "why", "background", "anti-pattern",
        "bad", "good", "quick reference",
    )
    for line in body.splitlines():
        match = re.match(r"^#{2,4}\s+(.+?)\s*$", line)
        if not match:
            continue
        title = match.group(1).strip()
        if any(keyword in title.lower() for keyword in keywords):
            candidates.append(title)
    return candidates[:4]


def _structural_findings(
    rules: list[Rule],
    metrics: list[RuleMetric],
) -> list[AuditFinding]:
    findings: list[AuditFinding] = []
    metrics_by_id = {metric.rule_id: metric for metric in metrics}
    for rule in rules:
        combined = f"{rule.name} {rule.description} {rule.body}".lower()
        normalized = " ".join(_tokens(combined))
        consequence = any(marker in combined for marker in HIGH_CONSEQUENCE_MARKERS)
        if not rule.description or rule.description.strip().lower() == rule.name.strip().lower():
            findings.append(AuditFinding(
                "weak-description", "medium", [rule.id],
                "Rule has no useful description",
                "Add a concise statement of the behavior the agent must follow.",
            ))
        if len(rule.body.strip()) < 20:
            findings.append(AuditFinding(
                "short-body", "medium", [rule.id],
                "Rule body is too short to be reliably actionable",
                "State the required behavior and when it applies.",
                f"{len(rule.body.strip())} characters",
            ))
        if any(phrase in normalized for phrase in GENERIC_RULES) and not consequence:
            findings.append(AuditFinding(
                "generic-guidance", "low", [rule.id],
                "Rule resembles baseline guidance modern coding models usually follow",
                "Archive it only if you have not observed violations; otherwise make the failure mode specific.",
            ))
        if any(marker in combined for marker in PREFERENCE_MARKERS) and not consequence:
            findings.append(AuditFinding(
                "likely-preference", "low", [rule.id],
                "Rule uses preference-like language rather than a hard constraint",
                "Review whether this belongs in a preference pack.",
            ))
        metric = metrics_by_id[rule.id]
        if metric.estimated_tokens >= 500:
            review_sections = _reviewable_sections(rule.body)
            section_text = (
                f" Review sections: {', '.join(review_sections)}."
                if review_sections
                else " Review repeated rationale and long examples."
            )
            if metric.risk == "high":
                preservation = "Preserve every prohibition, required safeguard, and credential definition."
            else:
                preservation = "Preserve the core directive, exceptions, and actionable alternatives."
            recent_text = (
                f" · recently compressed ~{metric.recent_before_tokens}→"
                f"{metric.estimated_tokens} (-{metric.recent_saved_tokens})"
                if metric.recent_saved_tokens
                else ""
            )
            findings.append(AuditFinding(
                "large-rule", "low", [rule.id],
                "Rule is a major contributor to prompt context",
                f"{preservation}{section_text}",
                f"~{metric.estimated_tokens} tokens · {metric.percent_of_total:.0f}% of total · "
                f"{metric.risk} risk · potential savings "
                f"~{metric.estimated_savings_low}-{metric.estimated_savings_high} tokens"
                f"{recent_text}",
            ))
    return findings


def _overlap_findings(rules: list[Rule]) -> list[AuditFinding]:
    findings: list[AuditFinding] = []
    exact_pairs: set[frozenset[str]] = set()
    for group in _exact_duplicate_groups(rules):
        ids = tuple(sorted(rule.id for rule in group))
        for index, left in enumerate(ids):
            for right in ids[index + 1:]:
                exact_pairs.add(frozenset((left, right)))
        findings.append(AuditFinding(
            "exact-duplicate", "high", list(ids),
            "Rules have identical normalized bodies",
            "Keep one canonical rule and remove the duplicates after creating a backup.",
        ))

    for index, left in enumerate(rules):
        for right in rules[index + 1:]:
            if left.scope != right.scope:
                continue
            if frozenset((left.id, right.id)) in exact_pairs:
                continue
            similarity = _jaccard(left, right)
            if similarity >= 0.72:
                findings.append(AuditFinding(
                    "high-overlap", "medium", sorted([left.id, right.id]),
                    "Rules have substantial lexical overlap",
                    "Review them together and merge only if their intent and scope are equivalent.",
                    f"similarity {similarity:.0%}",
                ))
    return findings


def _exact_duplicate_groups(rules: list[Rule]) -> list[list[Rule]]:
    groups: dict[tuple[str, str], list[Rule]] = {}
    for rule in rules:
        fingerprint = re.sub(r"\s+", " ", rule.body.strip())
        if fingerprint:
            groups.setdefault((rule.scope, fingerprint), []).append(rule)
    return [group for group in groups.values() if len(group) > 1]


def _jaccard(left: Rule, right: Rule) -> float:
    left_tokens = set(_tokens(f"{left.description} {left.body}"))
    right_tokens = set(_tokens(f"{right.description} {right.body}"))
    if len(left_tokens) < 5 or len(right_tokens) < 5:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _tokens(text: str) -> list[str]:
    return [
        token for token in re.findall(r"[a-z0-9][a-z0-9_-]+", text.lower())
        if token not in STOP_WORDS
    ]


def _normalize(text: str) -> str:
    return " ".join(_tokens(text))


def _rule_sort_key(rule: Rule) -> tuple[str, str]:
    return (rule.id, str(rule.file_path or ""))


def _dedupe_rule_paths(rules: list[Rule]) -> list[Rule]:
    by_path: dict[str, Rule] = {}
    for rule in rules:
        by_path[str(rule.file_path or rule.id)] = rule
    return list(by_path.values())


def _scope_ai_dir(config: GlobalConfig, project_name: str | None) -> Path:
    if not project_name:
        return config.global_ai_dir
    project = config.get_project(project_name)
    if not project:
        raise ValueError(f"Project '{project_name}' not found")
    return project.full_ai_path


def _create_backup(
    ai_dir: Path,
    plan: CompressionPlan,
    removable: list[Path],
) -> Path:
    backups_dir = ai_dir / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    backup = backups_dir / f"{stamp}-compress"
    suffix = 2
    while backup.exists():
        backup = backups_dir / f"{stamp}-compress-{suffix}"
        suffix += 1
    backup.mkdir()

    rules_dir = ai_dir / "rules"
    if rules_dir.exists():
        shutil.copytree(rules_dir, backup / "rules")
    rules_md = ai_dir / "rules.md"
    if rules_md.exists():
        shutil.copy2(rules_md, backup / "rules.md")

    files = []
    for path in sorted((backup / "rules").glob("*.md")) if (backup / "rules").exists() else []:
        files.append({
            "path": f"rules/{path.name}",
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        })
    if (backup / "rules.md").exists():
        path = backup / "rules.md"
        files.append({"path": "rules.md", "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})

    manifest = {
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dotai_version": __version__,
        "scope": plan.scope,
        "reason": "compress",
        "source": str(ai_dir),
        "files": files,
        "planned_removals": [str(path.relative_to(ai_dir)) for path in removable],
        "planned_tokens_before": plan.estimated_tokens_before,
        "planned_tokens_after": plan.estimated_tokens_after,
    }
    (backup / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return backup


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_recent_compression(ai_dir: Path) -> dict[str, dict]:
    """Load the newest completed compression record for each current rule."""
    backups_dir = ai_dir / "backups"
    if not backups_dir.is_dir():
        return {}
    recent: dict[str, dict] = {}
    for backup in sorted(backups_dir.glob("*-compress*"), reverse=True)[:20]:
        manifest_path = backup / "manifest.json"
        if not manifest_path.is_file():
            continue
        try:
            manifest = json.loads(manifest_path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        status = manifest.get("status")
        changes = manifest.get("changes", [])
        if status is None:
            scope = str(manifest.get("scope", "global"))
            before_rules = load_rules_from_dir(backup / "rules", scope)
            after_rules = load_rules_from_dir(ai_dir / "rules", scope)
            before_by_id = {rule.id: rule for rule in before_rules}
            changes = []
            for after in after_rules:
                before = before_by_id.get(after.id)
                if not before or not before.file_path or not after.file_path:
                    continue
                before_sha = _file_sha256(before.file_path)
                after_sha = _file_sha256(after.file_path)
                if before_sha == after_sha:
                    continue
                before_tokens = estimate_tokens(before.to_prompt())
                after_tokens = estimate_tokens(after.to_prompt())
                changes.append({
                    "rule_id": after.id,
                    "after_sha256": after_sha,
                    "before_tokens": before_tokens,
                    "after_tokens": after_tokens,
                    "saved_tokens": max(0, before_tokens - after_tokens),
                })
        elif status != "complete":
            continue
        for change in changes:
            rule_id = str(change.get("rule_id", ""))
            if not rule_id or rule_id in recent or not change.get("after_sha256"):
                continue
            recent[rule_id] = {
                **change,
                "completed_at": manifest.get("completed_at") or manifest.get("created_at", ""),
            }
    return recent
