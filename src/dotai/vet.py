"""Vet imported skills for security risks.

Wraps ai-skill-audit (https://pypi.org/project/ai-skill-audit/) to scan
skill files for credential leakage, RCE, data exfiltration, and other
malicious behaviors.

Returns a VetReport with findings and severity. Does NOT block
installation — the user decides whether to proceed.
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class Finding:
    severity: Severity
    category: str
    description: str
    file: str
    line: int | None = None
    match: str = ""


@dataclass
class VetReport:
    findings: list[Finding] = field(default_factory=list)
    grade: str = ""
    trust_score: float = 1.0

    @property
    def has_critical(self) -> bool:
        return any(f.severity == Severity.CRITICAL for f in self.findings)

    @property
    def has_high(self) -> bool:
        return any(f.severity in (Severity.CRITICAL, Severity.HIGH) for f in self.findings)

    @property
    def is_clean(self) -> bool:
        return len(self.findings) == 0

    def summary(self) -> dict[Severity, int]:
        counts: dict[Severity, int] = {}
        for f in self.findings:
            counts[f.severity] = counts.get(f.severity, 0) + 1
        return counts


# Categories that indicate critical threats (warrant blocking install)
_CRITICAL_CATEGORIES = {"EXFILTRATION", "OBFUSCATION", "SUSPICIOUS_URL", "INJECTION",
                        "PERSISTENCE", "HIJACKING"}

# Categories that indicate high-severity threats (warrant warning)
_HIGH_CATEGORIES = {"SECRET", "DESTRUCTIVE"}

# Everything else is medium
_MEDIUM_CATEGORIES = {"PRIVILEGE", "ENTROPY"}


def _classify_finding(category: str) -> Severity:
    """Map ai-skill-audit category to severity."""
    cat = category.upper()
    if cat in _CRITICAL_CATEGORIES:
        return Severity.CRITICAL
    if cat in _HIGH_CATEGORIES:
        return Severity.HIGH
    if cat in _MEDIUM_CATEGORIES:
        return Severity.MEDIUM
    return Severity.MEDIUM


def _vet_with_skill_audit(path: Path) -> VetReport:
    """Vet using ai-skill-audit's analyze_file API."""
    from skill_audit.analyzer import analyze_file

    report = VetReport()

    # Collect all auditable files
    if path.is_file():
        files = [path]
    else:
        exts = {".md"}
        files = [f for f in path.rglob("*") if f.is_file() and f.suffix in exts]
        # Also try the path itself if it's a directory with a single skill
        if not files:
            return report

    for file in files:
        try:
            card = analyze_file(file)
        except Exception:
            continue

        report.grade = card.grade
        label = str(file.relative_to(path)) if path.is_dir() else file.name

        # Extract trust dimension findings
        for dim in card.dimensions:
            if dim.name != "trust":
                continue

            report.trust_score = dim.score

            for suggestion in dim.suggestions:
                # Suggestions are formatted as "[CATEGORY] description"
                category = "UNKNOWN"
                description = suggestion
                if suggestion.startswith("[") and "]" in suggestion:
                    bracket_end = suggestion.index("]")
                    category = suggestion[1:bracket_end]
                    description = suggestion[bracket_end + 1:].strip()

                severity = _classify_finding(category)
                report.findings.append(Finding(
                    severity=severity,
                    category=category,
                    description=description,
                    file=label,
                ))

    return report


def vet_skill(path: Path) -> VetReport:
    """Vet a skill file or directory for security risks.

    Uses ai-skill-audit if installed, providing comprehensive trust scanning
    with grading across completeness, clarity, actionability, safety,
    testability, and trust dimensions.

    Returns a VetReport with all findings.
    """
    try:
        return _vet_with_skill_audit(path)
    except ImportError:
        # ai-skill-audit not installed — return empty report with warning
        report = VetReport()
        report.findings.append(Finding(
            severity=Severity.LOW,
            category="SETUP",
            description="ai-skill-audit not installed. Run: pip install ai-skill-audit",
            file=str(path),
        ))
        return report


def format_report(report: VetReport) -> str:
    """Format a VetReport as a human-readable string for terminal output."""
    if report.is_clean:
        return "No security issues found."

    lines: list[str] = []
    summary = report.summary()

    # Header with grade if available
    total = len(report.findings)
    header = f"Found {total} security finding(s)"
    if report.grade:
        header += f" (grade: {report.grade}, trust: {report.trust_score:.0%})"
    header += ":"
    lines.append(header)

    for sev in (Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW):
        count = summary.get(sev, 0)
        if count:
            lines.append(f"  {sev.value.upper()}: {count}")
    lines.append("")

    # Group by severity
    for sev in (Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW):
        sev_findings = [f for f in report.findings if f.severity == sev]
        if not sev_findings:
            continue

        lines.append(f"[{sev.value.upper()}]")
        for f in sev_findings:
            lines.append(f"  [{f.category}] {f.description}")
        lines.append("")

    return "\n".join(lines)
