"""Preference / taste packs — soft, borrowable style priors.

Preference packs capture micro-taste that hard rules are the wrong fit for:
CLI stack choices, design micro-details, export style, etc.

Layout:
  ~/.ai/preferences/<id>.md          # single-file pack
  ~/.ai/preferences/<id>/main.md     # folder pack
  ~/.ai/preferences-active.json      # globally active pack ids

  <project>/.ai/preferences/         # project packs (override same id)
  <project>/.ai/preferences-active.json

Precedence when generating code:
  hard rules > freeform rules.md > active preference packs > model default
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from .models import GlobalConfig, PreferencePack
from .utils import generate_id

ACTIVE_FILE = "preferences-active.json"
SOURCES_FILE = ".dotai-pref-sources.json"


def _parse_frontmatter(content: str) -> tuple[dict[str, str], str]:
    frontmatter: dict[str, str] = {}
    body = content
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].strip().split("\n"):
                if ":" in line:
                    key, value = line.split(":", 1)
                    frontmatter[key.strip().lower()] = value.strip()
            body = parts[2].strip()
    return frontmatter, body


def parse_preference_file(file_path: Path, scope: str = "global") -> PreferencePack | None:
    """Parse a preference pack markdown file."""
    if not file_path.exists() or not file_path.is_file():
        return None

    content = file_path.read_text()
    fm, body = _parse_frontmatter(content)

    # Folder packs use main.md; id from parent dir name
    if file_path.name == "main.md" and file_path.parent.name:
        default_id = generate_id(file_path.parent.name)
    else:
        default_id = generate_id(file_path.stem)

    name = fm.get("name", file_path.stem.replace("-", " ").replace("_", " ").title())
    pack_id = generate_id(fm.get("id", default_id))
    description = fm.get("description", "")
    domain = fm.get("domain", "general").strip().lower() or "general"
    tags = [t.strip() for t in fm.get("tags", "").split(",") if t.strip()]
    enabled = fm.get("enabled", "true").lower() not in ("false", "no", "0")
    source = fm.get("source", "")
    confidence = None
    if "confidence" in fm:
        try:
            confidence = float(fm["confidence"])
        except ValueError:
            confidence = None

    if not description:
        for line in body.split("\n"):
            stripped = line.strip().strip("#*`[]-")
            if stripped and len(stripped) > 10:
                description = stripped[:120]
                break
        if not description:
            description = name

    return PreferencePack(
        id=pack_id,
        name=name,
        description=description,
        domain=domain,
        enabled=enabled,
        tags=tags,
        body=body,
        source=source,
        confidence=confidence,
        file_path=file_path,
        scope=scope,
    )


def load_preferences_from_dir(prefs_dir: Path, scope: str = "global") -> list[PreferencePack]:
    """Load all preference packs from a directory."""
    packs: list[PreferencePack] = []
    if not prefs_dir.exists():
        return packs

    seen_ids: set[str] = set()

    # Single-file packs
    for md_file in sorted(prefs_dir.glob("*.md")):
        pack = parse_preference_file(md_file, scope)
        if pack and pack.id not in seen_ids:
            packs.append(pack)
            seen_ids.add(pack.id)

    # Folder packs (main.md)
    for item in sorted(prefs_dir.iterdir()):
        if item.is_dir() and not item.name.startswith("."):
            main = item / "main.md"
            if main.exists():
                pack = parse_preference_file(main, scope)
                if pack and pack.id not in seen_ids:
                    packs.append(pack)
                    seen_ids.add(pack.id)

    return packs


def load_all_preferences(config: GlobalConfig) -> list[PreferencePack]:
    """Load global + project preference packs (project overrides same id)."""
    by_id: dict[str, PreferencePack] = {}
    for pack in load_preferences_from_dir(config.global_preferences_path, "global"):
        by_id[pack.id] = pack
    for project in config.projects:
        for pack in load_preferences_from_dir(project.preferences_path, project.name):
            by_id[pack.id] = pack  # project wins on id clash
    return list(by_id.values())


def _active_path(ai_dir: Path) -> Path:
    return ai_dir / ACTIVE_FILE


def load_active_pack_ids(ai_dir: Path) -> list[str]:
    """Load active pack ids from preferences-active.json."""
    path = _active_path(ai_dir)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
        packs = data.get("packs", [])
        return [str(p) for p in packs]
    except (json.JSONDecodeError, OSError):
        return []


def save_active_pack_ids(ai_dir: Path, pack_ids: list[str]) -> None:
    """Persist active pack ids."""
    ai_dir.mkdir(parents=True, exist_ok=True)
    path = _active_path(ai_dir)
    # Preserve order, unique
    seen: set[str] = set()
    ordered: list[str] = []
    for pid in pack_ids:
        if pid not in seen:
            ordered.append(pid)
            seen.add(pid)
    path.write_text(json.dumps({"packs": ordered}, indent=2) + "\n")


def resolve_active_pack_ids(
    config: GlobalConfig,
    project_name: str | None = None,
    project_path: Path | None = None,
    extra: list[str] | None = None,
) -> list[str]:
    """Resolve which pack ids are active for this context.

    Order: extra (session overlay) + project active + global active (deduped).
    """
    ordered: list[str] = []
    seen: set[str] = set()

    def _add(ids: list[str]) -> None:
        for i in ids:
            if i and i not in seen:
                ordered.append(i)
                seen.add(i)

    if extra:
        _add(extra)

    if project_path:
        _add(load_active_pack_ids(project_path / ".ai"))
    elif project_name:
        proj = config.get_project(project_name)
        if proj:
            _add(load_active_pack_ids(proj.full_ai_path))

    _add(load_active_pack_ids(config.global_ai_dir))
    return ordered


def resolve_preference_packs(
    config: GlobalConfig,
    project_name: str | None = None,
    project_path: Path | None = None,
    extra: list[str] | None = None,
) -> list[PreferencePack]:
    """Load active preference packs for primer/sync.

    Project packs override global packs with the same id.
    Only enabled packs are returned.
    """
    # Build lookup: project first so it wins
    by_id: dict[str, PreferencePack] = {}
    for pack in load_preferences_from_dir(config.global_preferences_path, "global"):
        by_id[pack.id] = pack

    if project_path:
        local_dir = project_path / ".ai" / "preferences"
        for pack in load_preferences_from_dir(local_dir, project_name or "local"):
            by_id[pack.id] = pack
    elif project_name:
        proj = config.get_project(project_name)
        if proj:
            for pack in load_preferences_from_dir(proj.preferences_path, project_name):
                by_id[pack.id] = pack

    active_ids = resolve_active_pack_ids(config, project_name, project_path, extra)
    if not active_ids:
        return []

    result: list[PreferencePack] = []
    for pid in active_ids:
        pack = by_id.get(pid)
        if pack and pack.enabled:
            result.append(pack)
    return result


def format_preferences_section(packs: list[PreferencePack], *, compact: bool = False) -> str:
    """Render active preference packs for agent primer."""
    if not packs:
        return ""

    lines = [
        "## Active Preference Packs (taste)",
        "",
        "Soft style/taste priors for this session. **Hard rules always win** if they conflict.",
        "Use these for micro-decisions (stack, structure, naming flavor) — not security or bans.",
        "",
    ]

    if compact:
        for pack in packs:
            domain = f" [{pack.domain}]" if pack.domain != "general" else ""
            src = f" — `{pack.file_path}`" if pack.file_path else ""
            lines.append(f"- **{pack.name}** (`{pack.id}`){domain}: {pack.description}{src}")
        lines.append("")
        lines.append("Read each pack file fully when working in its domain.")
        lines.append("")
    else:
        for pack in packs:
            lines.append(pack.to_prompt())
            lines.append("")

    return "\n".join(lines)


def create_preference_pack(
    dest_dir: Path,
    name: str,
    *,
    description: str = "",
    domain: str = "general",
    body: str = "",
    tags: list[str] | None = None,
    source: str = "local",
    pack_id: str | None = None,
) -> Path:
    """Create a new preference pack file. Returns path written."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    pid = generate_id(pack_id or name)
    path = dest_dir / f"{pid}.md"

    desc = description or f"Preference pack: {name}"
    default_body = body or (
        f"## Soft preferences\n\n"
        f"These are style/taste defaults for **{name}**. Hard rules always take precedence.\n\n"
        f"### Stack & tools\n\n"
        f"- (add your preferred tools here)\n\n"
        f"### Structure\n\n"
        f"- (add layout / file organization prefs)\n\n"
        f"### Style\n\n"
        f"- (add naming, exports, formatting prefs)\n"
    )

    fm = [
        "---",
        f"name: {name}",
        f"id: {pid}",
        f"description: {desc}",
        f"domain: {domain}",
        f"source: {source}",
    ]
    if tags:
        fm.append(f"tags: {', '.join(tags)}")
    fm.append("---")

    path.write_text("\n".join(fm) + "\n\n" + default_body.strip() + "\n")
    return path


def activate_pack(
    config: GlobalConfig,
    pack_id: str,
    *,
    project_name: str | None = None,
    project_path: Path | None = None,
    global_scope: bool = False,
) -> Path:
    """Add pack_id to the active list. Returns path of active file updated."""
    if global_scope or (not project_name and not project_path):
        ai_dir = config.global_ai_dir
    elif project_path:
        ai_dir = project_path / ".ai"
    else:
        proj = config.get_project(project_name or "")
        if not proj:
            raise ValueError(f"Project '{project_name}' not found")
        ai_dir = proj.full_ai_path

    current = load_active_pack_ids(ai_dir)
    if pack_id not in current:
        current.append(pack_id)
    save_active_pack_ids(ai_dir, current)
    return _active_path(ai_dir)


def deactivate_pack(
    config: GlobalConfig,
    pack_id: str,
    *,
    project_name: str | None = None,
    project_path: Path | None = None,
    global_scope: bool = False,
) -> Path:
    """Remove pack_id from the active list."""
    if global_scope or (not project_name and not project_path):
        ai_dir = config.global_ai_dir
    elif project_path:
        ai_dir = project_path / ".ai"
    else:
        proj = config.get_project(project_name or "")
        if not proj:
            raise ValueError(f"Project '{project_name}' not found")
        ai_dir = proj.full_ai_path

    current = [p for p in load_active_pack_ids(ai_dir) if p != pack_id]
    save_active_pack_ids(ai_dir, current)
    return _active_path(ai_dir)


def find_pack(config: GlobalConfig, pack_id: str) -> PreferencePack | None:
    """Find a pack by id across global and projects."""
    pid = generate_id(pack_id)
    for pack in load_all_preferences(config):
        if pack.id == pid:
            return pack
    # Also search unregistered project-local dirs is not available; search global only paths
    for pack in load_preferences_from_dir(config.global_preferences_path, "global"):
        if pack.id == pid:
            return pack
    return None


def record_pref_source(prefs_dir: Path, pack_key: str, source_url: str, source_type: str = "git") -> None:
    prefs_dir.mkdir(parents=True, exist_ok=True)
    path = prefs_dir / SOURCES_FILE
    data: dict = {}
    if path.exists():
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            data = {}
    data[pack_key] = {"url": source_url, "type": source_type}
    path.write_text(json.dumps(data, indent=2) + "\n")


def pull_preference_pack(
    source: str,
    dest_dir: Path,
    *,
    pack_name: str | None = None,
    domain: str = "general",
) -> list[Path]:
    """Install preference pack(s) from a local path or git URL.

    Returns list of installed pack file paths.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    source_path = Path(source).expanduser()
    installed: list[Path] = []

    if source_path.exists():
        installed = _install_from_local(source_path, dest_dir, pack_name=pack_name, domain=domain)
        for p in installed:
            record_pref_source(dest_dir, p.stem if p.suffix == ".md" else p.parent.name,
                               str(source_path), "local")
        return installed

    # Git clone
    import subprocess
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp) / "repo"
        subprocess.run(
            ["git", "clone", "--depth", "1", source, str(tmp_path)],
            check=True,
            capture_output=True,
        )
        # Prefer preferences/ subdirectory if present
        root = tmp_path / "preferences" if (tmp_path / "preferences").is_dir() else tmp_path
        if pack_name:
            candidate = root / pack_name
            if not candidate.exists():
                candidate = root / f"{pack_name}.md"
            if not candidate.exists():
                raise FileNotFoundError(f"Pack '{pack_name}' not found in {source}")
            installed = _install_from_local(candidate, dest_dir, pack_name=pack_name, domain=domain)
        else:
            installed = _install_from_local(root, dest_dir, pack_name=None, domain=domain)

        for p in installed:
            key = p.stem if p.suffix == ".md" else p.parent.name
            record_pref_source(dest_dir, key, source, "git")

    return installed


def _install_from_local(
    source: Path,
    dest_dir: Path,
    *,
    pack_name: str | None,
    domain: str,
) -> list[Path]:
    """Copy pack file(s) from a local path into dest_dir."""
    installed: list[Path] = []

    if source.is_file():
        name = pack_name or source.stem
        pid = generate_id(name)
        dest = dest_dir / f"{pid}.md"
        content = source.read_text()
        # Ensure frontmatter has id/domain if missing
        content = _ensure_pack_frontmatter(content, name=name, pack_id=pid, domain=domain, source=str(source))
        dest.write_text(content)
        installed.append(dest)
        return installed

    if not source.is_dir():
        raise FileNotFoundError(f"Source not found: {source}")

    # Directory of packs or a single folder pack
    if (source / "main.md").exists():
        name = pack_name or source.name
        pid = generate_id(name)
        dest = dest_dir / pid
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(source, dest)
        main = dest / "main.md"
        main.write_text(
            _ensure_pack_frontmatter(
                main.read_text(), name=name, pack_id=pid, domain=domain, source=str(source)
            )
        )
        installed.append(main)
        return installed

    # Multiple .md files
    md_files = sorted(source.glob("*.md"))
    folder_packs = [
        d for d in source.iterdir()
        if d.is_dir() and (d / "main.md").exists() and not d.name.startswith(".")
    ]

    if pack_name:
        target = source / f"{pack_name}.md"
        if not target.exists():
            target = source / pack_name
        if not target.exists():
            raise FileNotFoundError(f"Pack '{pack_name}' not found in {source}")
        return _install_from_local(target, dest_dir, pack_name=pack_name, domain=domain)

    for md in md_files:
        installed.extend(_install_from_local(md, dest_dir, pack_name=None, domain=domain))
    for folder in folder_packs:
        installed.extend(_install_from_local(folder, dest_dir, pack_name=None, domain=domain))

    if not installed:
        # Treat whole dir body as one pack: concatenate markdown or use README
        readme = source / "README.md"
        if readme.exists():
            return _install_from_local(
                readme, dest_dir, pack_name=pack_name or source.name, domain=domain
            )
        raise FileNotFoundError(f"No preference packs found in {source}")

    return installed


def _ensure_pack_frontmatter(
    content: str,
    *,
    name: str,
    pack_id: str,
    domain: str,
    source: str,
) -> str:
    """Inject or update essential frontmatter fields."""
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            fm_lines = parts[1].strip().split("\n") if parts[1].strip() else []
            keys = {line.split(":")[0].strip().lower() for line in fm_lines if ":" in line}
            if "name" not in keys:
                fm_lines.insert(0, f"name: {name}")
            if "id" not in keys:
                fm_lines.append(f"id: {pack_id}")
            if "domain" not in keys:
                fm_lines.append(f"domain: {domain}")
            if "source" not in keys and source:
                fm_lines.append(f"source: {source}")
            return "---\n" + "\n".join(fm_lines) + "\n---" + parts[2]

    return (
        f"---\nname: {name}\nid: {pack_id}\ndomain: {domain}\n"
        f"description: Imported preference pack\nsource: {source}\n---\n\n"
        f"{content.strip()}\n"
    )


def distill_prefs_from_text(
    text: str,
    *,
    name: str,
    domain: str = "general",
    source: str = "",
) -> str:
    """Build a preference pack markdown body from freeform text (no LLM).

    Structural: wrap content as soft preferences with a precedence notice.
    """
    cleaned = text.strip()
    # Drop huge auto-generated primer blobs
    if "This project uses a structured knowledge system" in cleaned:
        # Keep only non-generated looking sections if possible
        pass

    body = (
        "## Soft preferences\n\n"
        "Distilled / imported taste. **Hard rules always take precedence.**\n\n"
        f"{cleaned}\n"
    )
    fm = [
        "---",
        f"name: {name}",
        f"id: {generate_id(name)}",
        f"description: Distilled preferences from {source or 'source'}",
        f"domain: {domain}",
    ]
    if source:
        fm.append(f"source: {source}")
    fm.append("---")
    return "\n".join(fm) + "\n\n" + body
