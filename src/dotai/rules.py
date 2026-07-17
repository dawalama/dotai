"""Rule parsing and management.

Rules are structured coding guidelines stored as individual markdown files
in ~/.ai/rules/ (global) or <project>/.ai/rules/ (project-scoped).

Each rule file has frontmatter (name, description, globs, tags) and a body
that agents can directly consume and enforce.
"""

import re
from pathlib import Path

from .models import GlobalConfig, Rule
from .utils import generate_id as generate_rule_id


def parse_rule_file(file_path: Path, scope: str = "global") -> Rule | None:
    """Parse a rule from a markdown file.

    Expected format:
    ---
    name: No useEffect
    description: Ban direct useEffect calls in React components
    globs: *.tsx, *.ts
    tags: react, hooks
    ---

    Never call `useEffect` directly...
    [rest of rule body]
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
    globs = [g.strip() for g in frontmatter.get("globs", "").split(",") if g.strip()]
    enabled = frontmatter.get("enabled", "true").lower() not in ("false", "no", "0")

    if not description:
        # Use first non-empty line of body as description
        for line in body.split("\n"):
            stripped = line.strip().strip("#*`[]")
            if stripped:
                description = stripped[:120]
                break

    return Rule(
        id=generate_rule_id(name),
        name=name,
        description=description,
        enabled=enabled,
        tags=tags,
        globs=globs,
        body=body,
        file_path=file_path,
        scope=scope,
    )


def load_rules_from_dir(rules_dir: Path, scope: str = "global") -> list[Rule]:
    """Load all rules from a directory."""
    rules = []
    if not rules_dir.exists():
        return rules

    for md_file in sorted(rules_dir.glob("*.md")):
        rule = parse_rule_file(md_file, scope)
        if rule:
            rules.append(rule)

    return rules


def load_all_rules(config: GlobalConfig) -> list[Rule]:
    """Load all rules from global and project directories."""
    rules = []

    # Global rules
    rules.extend(load_rules_from_dir(config.global_rules_path, "global"))

    # Project rules
    for project in config.projects:
        rules.extend(load_rules_from_dir(project.rules_path, project.name))

    return rules


def resolve_rules_for_project(config: GlobalConfig, project_name: str | None = None) -> list[Rule]:
    """Resolve the active rule set for a project.

    - Includes all enabled global rules, minus any the project has disabled
    - Includes all enabled project-specific rules
    - Respects the `enabled` field in each rule's frontmatter
    """
    global_rules = load_rules_from_dir(config.global_rules_path, "global")

    # Get project-level disabled list
    disabled_ids: set[str] = set()
    project_rules: list[Rule] = []

    if project_name:
        proj = config.get_project(project_name)
        if proj:
            disabled_ids = set(proj.disabled_rules)
            project_rules = load_rules_from_dir(proj.rules_path, project_name)

    # Filter: enabled globally + not disabled by project
    active = [r for r in global_rules if r.enabled and r.id not in disabled_ids]
    active.extend(r for r in project_rules if r.enabled)

    return active


def toggle_rule_global(rule_id: str, rules_dir: Path, enabled: bool) -> bool:
    """Toggle a rule's enabled state in its frontmatter.

    Returns True if the rule was found and updated.
    """
    rule_path = rules_dir / f"{rule_id}.md"
    if not rule_path.exists():
        return False

    content = rule_path.read_text()
    if not content.startswith("---"):
        return False

    parts = content.split("---", 2)
    if len(parts) < 3:
        return False

    fm_lines = parts[1].strip().split("\n")
    enabled_str = "true" if enabled else "false"

    # Replace existing enabled line or append one
    found = False
    for i, line in enumerate(fm_lines):
        if line.startswith("enabled:"):
            fm_lines[i] = f"enabled: {enabled_str}"
            found = True
            break

    if not found:
        fm_lines.append(f"enabled: {enabled_str}")

    new_fm = "\n".join(fm_lines)
    rule_path.write_text(f"---\n{new_fm}\n---{parts[2]}")
    return True


def toggle_rule_for_project(config: GlobalConfig, project_name: str, rule_id: str, disabled: bool) -> bool:
    """Disable or re-enable a global rule for a specific project.

    Updates the project's disabled_rules list in the config.
    Returns True if the config was changed.
    """
    from .store import save_config

    proj = config.get_project(project_name)
    if not proj:
        return False

    if disabled and rule_id not in proj.disabled_rules:
        proj.disabled_rules.append(rule_id)
        save_config(config)
        return True
    elif not disabled and rule_id in proj.disabled_rules:
        proj.disabled_rules.remove(rule_id)
        save_config(config)
        return True

    return False


def format_rule_markdown(
    name: str,
    description: str,
    body: str,
    globs: list[str] | None = None,
    tags: list[str] | None = None,
    enabled: bool = True,
) -> str:
    """Build a structured rule file as markdown (frontmatter + body)."""
    fm_lines = [
        "---",
        f"name: {name}",
        f"description: {description}",
    ]
    if globs:
        fm_lines.append(f"globs: {', '.join(globs)}")
    if tags:
        fm_lines.append(f"tags: {', '.join(tags)}")
    if not enabled:
        fm_lines.append("enabled: false")
    fm_lines.append("---")
    return "\n".join(fm_lines) + "\n\n" + body.strip() + "\n"


def build_rule_from_learning(
    name: str,
    dest_dir: Path,
    issue: str,
    correction: str,
    description: str | None = None,
    globs: list[str] | None = None,
    tags: list[str] | None = None,
) -> tuple[Path, str]:
    """Build path + markdown for a structured rule from issue/correction.

    Does not write to disk.
    """
    rule_id = generate_rule_id(name)
    dest_path = dest_dir / f"{rule_id}.md"

    desc = (description or correction).strip()
    if len(desc) > 120:
        desc = desc[:117] + "..."

    body = (
        f"### Rule: `{name}`\n\n"
        f"_{desc}_\n\n"
        f"**Issue:** {issue.strip()}\n\n"
        f"**Correction:** {correction.strip()}\n\n"
        "Always follow the correction. Do not repeat the issue.\n"
    )

    auto_tags = tags if tags is not None else _detect_tags(f"{issue}\n{correction}")
    content = format_rule_markdown(
        name=name,
        description=desc,
        body=body,
        globs=globs,
        tags=auto_tags or None,
    )
    return dest_path, content


def build_rule_from_directive(
    name: str,
    dest_dir: Path,
    directive: str,
    description: str | None = None,
    globs: list[str] | None = None,
    tags: list[str] | None = None,
) -> tuple[Path, str]:
    """Build a structured rule from a proactive engineering directive.

    Unlike a learning, a directive does not require a prior mistake. This is the
    primary capture path for standards, architectural choices, and developer taste.
    Does not write to disk.
    """
    rule_id = generate_rule_id(name)
    dest_path = dest_dir / f"{rule_id}.md"
    clean_directive = directive.strip()
    desc = (description or clean_directive).strip()
    if len(desc) > 120:
        desc = desc[:117] + "..."

    body = (
        f"### Rule: `{name}`\n\n"
        f"_{desc}_\n\n"
        f"**Directive:** {clean_directive}\n"
    )
    auto_tags = tags if tags is not None else _detect_tags(clean_directive)
    content = format_rule_markdown(
        name=name,
        description=desc,
        body=body,
        globs=globs,
        tags=auto_tags or None,
    )
    return dest_path, content


def create_rule_from_directive(
    name: str,
    dest_dir: Path,
    directive: str,
    description: str | None = None,
    globs: list[str] | None = None,
    tags: list[str] | None = None,
) -> Path:
    """Create a structured rule from a proactive engineering directive."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path, content = build_rule_from_directive(
        name=name,
        dest_dir=dest_dir,
        directive=directive,
        description=description,
        globs=globs,
        tags=tags,
    )
    dest_path.write_text(content)
    return dest_path


def create_rule_from_learning(
    name: str,
    dest_dir: Path,
    issue: str,
    correction: str,
    description: str | None = None,
    globs: list[str] | None = None,
    tags: list[str] | None = None,
) -> Path:
    """Create a structured rule from an issue/correction pair.

    This is the primary capture path for `dotai learn`. Writes to
    ``dest_dir/<rule-id>.md``.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path, content = build_rule_from_learning(
        name=name,
        dest_dir=dest_dir,
        issue=issue,
        correction=correction,
        description=description,
        globs=globs,
        tags=tags,
    )
    dest_path.write_text(content)
    return dest_path


def find_duplicate_rules(
    config: GlobalConfig,
    name: str,
    description: str = "",
    project_name: str | None = None,
) -> list[Rule]:
    """Find existing rules that likely duplicate a new learning.

    Matches by rule id, exact name (case-insensitive), or substantial
    description overlap. Used as a quality gate before write.
    """
    rule_id = generate_rule_id(name)
    name_lower = name.strip().lower()
    desc_lower = description.strip().lower()

    if project_name:
        existing = resolve_rules_for_project(config, project_name)
        # Also include disabled global rules for the project so we catch id clashes
        all_rules = load_all_rules(config)
        seen = {r.id for r in existing}
        for r in all_rules:
            if r.id not in seen and (r.scope == "global" or r.scope == project_name):
                existing.append(r)
                seen.add(r.id)
    else:
        existing = load_all_rules(config)

    matches: list[Rule] = []
    for rule in existing:
        if rule.id == rule_id:
            matches.append(rule)
            continue
        if rule.name.strip().lower() == name_lower:
            matches.append(rule)
            continue
        if desc_lower and rule.description:
            rd = rule.description.strip().lower()
            if desc_lower == rd:
                matches.append(rule)
            elif len(desc_lower) >= 20 and (desc_lower in rd or rd in desc_lower):
                matches.append(rule)
    return matches


def check_rule_quality(config: GlobalConfig) -> list[dict]:
    """Scan for empty bodies, missing descriptions, and duplicate ids/names.

    Returns a list of finding dicts: {severity, rule_id, message}.
    """
    rules = load_all_rules(config)
    findings: list[dict] = []
    by_id: dict[str, list[Rule]] = {}
    by_name: dict[str, list[Rule]] = {}

    for rule in rules:
        by_id.setdefault(rule.id, []).append(rule)
        by_name.setdefault(rule.name.strip().lower(), []).append(rule)

        if not rule.description or rule.description.strip() == rule.name:
            findings.append({
                "severity": "warn",
                "rule_id": rule.id,
                "message": "Missing or weak description",
            })
        if not rule.body or len(rule.body.strip()) < 20:
            findings.append({
                "severity": "warn",
                "rule_id": rule.id,
                "message": "Empty or very short rule body",
            })

    for rid, group in by_id.items():
        if len(group) > 1:
            scopes = ", ".join(f"{r.scope}" for r in group)
            findings.append({
                "severity": "error",
                "rule_id": rid,
                "message": f"Duplicate rule id across scopes: {scopes}",
            })

    for name, group in by_name.items():
        if len(group) > 1:
            ids = ", ".join(r.id for r in group)
            findings.append({
                "severity": "warn",
                "rule_id": group[0].id,
                "message": f"Same name '{name}' on multiple rules: {ids}",
            })

    return findings


def load_rules_md(ai_dir: Path) -> str:
    """Load freeform rules.md content if present (empty string if missing)."""
    path = ai_dir / "rules.md"
    if path.exists():
        return path.read_text().strip()
    return ""


def build_rule_from_file(
    source_path: Path,
    name: str,
    dest_dir: Path,
    description: str | None = None,
    globs: list[str] | None = None,
    tags: list[str] | None = None,
) -> tuple[Path, str]:
    """Build path + markdown for a rule imported from an external file.

    Does not write to disk.
    """
    content = source_path.read_text().strip()
    rule_id = generate_rule_id(name)
    body = _extract_rule_body(content)

    if not description:
        for line in body.split("\n"):
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("|") or stripped.startswith("```") or not stripped:
                continue
            cleaned = re.sub(r"[*`\[\]]", "", stripped).strip()
            if cleaned and len(cleaned) > 10:
                description = cleaned[:120]
                break
        if not description:
            description = name

    if not tags:
        tags = _detect_tags(body)

    rule_content = format_rule_markdown(
        name=name,
        description=description,
        body=body,
        globs=globs,
        tags=tags or None,
    )
    return dest_dir / f"{rule_id}.md", rule_content


def create_rule_from_file(source_path: Path, name: str, dest_dir: Path,
                          description: str | None = None,
                          globs: list[str] | None = None,
                          tags: list[str] | None = None) -> Path:
    """Import an external file as a structured rule.

    Reads the source file, wraps it in proper frontmatter, and writes
    it to the rules directory.

    Returns the path to the created rule file.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path, rule_content = build_rule_from_file(
        source_path=source_path,
        name=name,
        dest_dir=dest_dir,
        description=description,
        globs=globs,
        tags=tags,
    )
    dest_path.write_text(rule_content)
    return dest_path


def _extract_rule_body(content: str) -> str:
    """Extract the actionable rule body, stripping leading prose/instructions."""
    # If the content already has frontmatter, strip it
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            return parts[2].strip()

    # Strip leading prose that looks like instructions about how to use the rule
    # (e.g., "Here's the exact rule you can copy-paste...")
    lines = content.split("\n")
    start = 0
    for i, line in enumerate(lines):
        # Start at the first heading, table, or code block
        if line.startswith("#") or line.startswith("|") or line.startswith("```"):
            start = i
            break
        # Or at a bold directive (like "**Never call...")
        if line.startswith("**") and not line.startswith("**Here"):
            start = i
            break

    body_lines = lines[start:]

    # Strip trailing prose/marketing (lines after the last code block, heading, or list item)
    end = len(body_lines)
    for i in range(len(body_lines) - 1, -1, -1):
        line = body_lines[i].strip()
        if line.startswith("#") or line.startswith("|") or line.startswith("```") or \
           line.startswith("- ") or line.startswith("**") or line == "":
            end = i + 1
            break

    return "\n".join(body_lines[:end]).strip()


def _detect_tags(content: str) -> list[str]:
    """Detect likely tags from rule content."""
    tags = []
    content_lower = content.lower()

    tag_hints = {
        "react": ["react", "useeffect", "usestate", "jsx", "tsx", "component"],
        "typescript": ["typescript", ".ts", "type ", "interface "],
        "python": ["python", "def ", "import ", ".py"],
        "testing": ["test", "spec", "jest", "pytest", "mock"],
        "security": ["xss", "injection", "auth", "csrf", "sanitiz"],
        "performance": ["performance", "lazy", "memo", "cache", "optimize"],
        "hooks": ["usememo", "usecallback", "useeffect", "usestate", "useref"],
        "css": ["css", "tailwind", "styled", "classname"],
    }

    for tag, keywords in tag_hints.items():
        if any(kw in content_lower for kw in keywords):
            tags.append(tag)

    return tags
