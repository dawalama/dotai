"""CLI commands for skills."""

from pathlib import Path
from typing import Optional

import typer
from rich.table import Table

from . import app, console


def _stage_tracked_skill(source: str, key: str, staging_dir: Path) -> Path:
    """Copy or clone one recorded skill into an isolated staging directory."""
    import shutil

    local = Path(source).expanduser()
    skill_id = key[:-3] if key.endswith(".md") else key
    if local.exists():
        candidates = (
            [local]
            if local.is_file()
            else [
                local / key,
                local / skill_id,
                local / "skills" / key,
                local / "skills" / skill_id,
                local,
            ]
        )
        selected = next((candidate for candidate in candidates if candidate.exists()), None)
        if not selected:
            raise FileNotFoundError(f"Tracked skill '{key}' not found in {source}")
        staged = staging_dir / selected.name
        if selected.is_file():
            shutil.copy2(selected, staged)
        else:
            shutil.copytree(selected, staged)
        return staged

    from ..skills import install_skill_from_repo

    return install_skill_from_repo(source, staging_dir, skill_id)


def _install_staged_skill(staged: Path, dest_dir: Path, key: str) -> Path:
    """Install a vetted staged skill while preserving its recorded identity."""
    import shutil

    from ..converter import (
        convert_claude_to_dotai,
        convert_plugin_to_dotai,
        detect_skill_format,
    )

    fmt = detect_skill_format(staged)
    if fmt == "claude-native":
        return convert_claude_to_dotai(staged, dest_dir)
    if fmt in ("claude-plugin", "cursor-plugin", "gemini-extension"):
        converted = convert_plugin_to_dotai(staged, dest_dir)
        if not converted:
            raise FileNotFoundError(f"No skills found while refreshing '{key}'")
        matching = next((path for path in converted if path.name == key), None)
        return matching or converted[0]

    dest = dest_dir / key
    if staged.is_file():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(staged, dest)
    else:
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(staged, dest)
    return dest


@app.command()
def skills(
    category: Optional[str] = typer.Option(None, "--category", "-c", help="Filter by category"),
):
    """List all available skills."""
    from ..store import load_config
    from ..skills import load_all_skills, _parse_category

    config = load_config()
    all_skills = load_all_skills(config)

    if category:
        cat = _parse_category(category)
        if cat:
            all_skills = [s for s in all_skills if s.category == cat]
        else:
            console.print(f"[red]Unknown category: {category}[/red]")
            raise typer.Exit(1)

    if not all_skills:
        console.print("[dim]No skills found. Run `dotai init` to seed default skills.[/dim]")
        return

    table = Table(title="Available Skills")
    table.add_column("Name", style="bold")
    table.add_column("Trigger", style="green")
    table.add_column("Category", style="magenta")
    table.add_column("Role", style="cyan")
    table.add_column("Scope", style="dim")
    table.add_column("Source", style="dim")
    table.add_column("Description")

    for skill in all_skills:
        # Shorten source for display
        source_display = ""
        if skill.source:
            src = skill.source
            if "github.com/" in src:
                # Show "user/repo" for GitHub URLs
                parts = src.rstrip("/").split("github.com/")[-1]
                source_display = parts.split(".git")[0]
            elif "/" in src:
                source_display = "~/" + src.split("/")[-1] if src.startswith("/") else src
            else:
                source_display = src

        table.add_row(
            skill.id,
            skill.trigger or "",
            skill.category.value if skill.category else "",
            skill.role or "",
            skill.scope,
            source_display,
            skill.description[:50],
        )

    console.print(table)


@app.command()
def install(
    source: Optional[str] = typer.Argument(None, help="Git repo URL or local path to install skill(s) from"),
    skill_name: Optional[str] = typer.Option(None, "--skill", "-s", help="Specific skill name within the repo"),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Install to a project instead of global"),
    skip_vet: bool = typer.Option(False, "--skip-vet", help="Skip security vetting of imported skills"),
    update: bool = typer.Option(
        False,
        "--update",
        "-u",
        help="Re-install skill(s) from recorded sources (.dotai-sources.json). Use with -s or alone for all.",
    ),
):
    """Install skills from a git repo or local directory.

    From a git repo:
      dotai install https://github.com/user/ai-skills
      dotai install https://github.com/user/ai-skills -s deploy

    From a local directory:
      dotai install ~/my-skills/review

    Re-install from tracked sources (team conventions repo):
      dotai install --update
      dotai install --update -s mvp
    """
    import shutil
    from ..store import load_config

    config = load_config()

    if project:
        proj = config.get_project(project)
        if not proj:
            console.print(f"[red]Project '{project}' not found[/red]")
            raise typer.Exit(1)
        dest_dir = proj.skills_path
    else:
        dest_dir = config.global_skills_path

    dest_dir.mkdir(parents=True, exist_ok=True)

    # --- Update from recorded sources ---
    if update:
        import tempfile

        from ..skills import load_sources, record_source
        from ..vet import format_report, vet_skill

        sources = load_sources(dest_dir)
        if not sources:
            console.print("[dim]No recorded skill sources to update. Install with a URL first.[/dim]")
            raise typer.Exit(1)

        keys = [skill_name] if skill_name else list(sources.keys())
        updated = 0
        for key in keys:
            meta = sources.get(key)
            if not meta:
                console.print(f"[yellow]No source recorded for '{key}'[/yellow]")
                continue
            url = meta.get("url", "")
            if not url:
                continue
            console.print(f"[dim]Updating from {url}...[/dim]")
            try:
                with tempfile.TemporaryDirectory() as tmp:
                    staged = _stage_tracked_skill(url, key, Path(tmp))
                    report = vet_skill(staged)
                    if not report.is_clean:
                        console.print(
                            f"\n[yellow]Security scan results for update[/yellow] {key}:"
                        )
                        console.print(format_report(report))
                        if report.should_block and not skip_vet:
                            console.print(
                                "[red]Update blocked; existing skill was preserved. "
                                "Use --skip-vet to override.[/red]"
                            )
                            continue
                        if report.should_warn and not skip_vet:
                            if not typer.confirm("Apply this update?"):
                                console.print("[dim]Existing skill preserved.[/dim]")
                                continue

                    installed = _install_staged_skill(staged, dest_dir, key)
                    record_source(
                        dest_dir,
                        installed.name,
                        url,
                        "local" if Path(url).expanduser().exists() else "git",
                    )
                    console.print(f"[green]Updated skill:[/green] {installed.name}")
                updated += 1
            except Exception as e:
                console.print(f"[red]Failed to update {key}: {e}[/red]")
        console.print(f"[green]Refreshed {updated} source(s)[/green]")
        console.print("[dim]Run `dotai sync` so agents pick up changes.[/dim]")
        return

    if not source:
        console.print("[red]Provide a source URL/path, or use --update[/red]")
        raise typer.Exit(1)

    source_path = Path(source).expanduser()
    if source_path.exists():
        # Local install
        dest_name = skill_name or source_path.name
        dest = dest_dir / dest_name

        # Vet before installing
        from ..vet import vet_skill, format_report
        report = vet_skill(source_path)
        if not report.is_clean:
            console.print(f"\n[yellow]Security scan results for[/yellow] {source_path.name}:")
            console.print(format_report(report))
            if report.should_block:
                console.print("[red bold]Audit recommends blocking this skill.[/red bold]")
                console.print("[red]Installation blocked. Use --skip-vet to override.[/red]")
                if not skip_vet:
                    raise typer.Exit(1)
            elif report.should_warn:
                console.print("[yellow bold]Audit recommends review before using.[/yellow bold]")
                if not skip_vet:
                    if not typer.confirm("Install anyway?"):
                        raise typer.Exit(1)

        if source_path.is_file():
            shutil.copy2(source_path, dest_dir / source_path.name)
            console.print(f"[green]Installed skill:[/green] {source_path.name}")
        else:
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(source_path, dest)
            console.print(f"[green]Installed skill folder:[/green] {dest_name}")
        console.print(f"  [dim]{dest}[/dim]")
    else:
        # Git repo install
        from ..skills import install_skill_from_repo

        try:
            dest = install_skill_from_repo(source, dest_dir, skill_name)
            console.print(f"[green]Installed from repo:[/green] {source}")
            console.print(f"  [dim]{dest}[/dim]")
        except FileNotFoundError as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(1)
        except Exception as e:
            console.print(f"[red]Failed to install: {e}[/red]")
            raise typer.Exit(1)

        # Vet after clone (source wasn't local)
        from ..vet import vet_skill, format_report
        report = vet_skill(dest)
        if not report.is_clean:
            console.print(f"\n[yellow]Security scan results:[/yellow]")
            console.print(format_report(report))
            if report.should_block:
                console.print("[red bold]Audit recommends blocking this skill.[/red bold]")
                if not skip_vet:
                    console.print("[red]Removing installed skill.[/red]")
                    shutil.rmtree(dest) if dest.is_dir() else dest.unlink()
                    raise typer.Exit(1)
            elif report.should_warn:
                console.print("[yellow bold]Audit recommends review before using.[/yellow bold]")
                if not skip_vet:
                    if not typer.confirm("Keep installed skill?"):
                        shutil.rmtree(dest) if dest.is_dir() else dest.unlink()
                        raise typer.Exit(1)

    # Auto-detect and convert skills from various formats
    from ..converter import detect_skill_format, convert_claude_to_dotai, convert_plugin_to_dotai
    from ..skills import record_source

    # Determine source label for tracking
    source_label = source if not source_path.exists() else str(source_path)
    source_type = "local" if source_path.exists() else "git"

    # Check if we just installed a plugin/extension or Claude-native skill(s)
    installed_path = dest_dir / (skill_name or source_path.name) if source_path.exists() else dest
    converted_files: list[Path] = []

    if installed_path.exists():
        fmt = detect_skill_format(installed_path)
        if fmt in ("claude-plugin", "cursor-plugin", "gemini-extension"):
            fmt_label = fmt.replace("-", " ").title()
            console.print(f"  [yellow]Detected {fmt_label} format, converting...[/yellow]")
            results = convert_plugin_to_dotai(installed_path, dest_dir)
            converted_files.extend(results)
            source_type = fmt
            console.print(f"  [green]Converted {len(results)} skill(s) to dotai format[/green]")
        elif fmt == "claude-native":
            console.print(f"  [yellow]Detected Claude-native format, converting...[/yellow]")
            result = convert_claude_to_dotai(installed_path, dest_dir)
            converted_files.append(result)
            console.print(f"  [green]Converted to dotai format[/green]")
        elif installed_path.is_dir():
            # Scan subdirectories for Claude-native skills (repo with multiple skills)
            for sub in sorted(installed_path.iterdir()):
                if sub.is_dir() and detect_skill_format(sub) == "claude-native":
                    result = convert_claude_to_dotai(sub, dest_dir)
                    converted_files.append(result)
            if converted_files:
                console.print(f"  [yellow]Detected {len(converted_files)} Claude-native skill(s), converted to dotai format[/yellow]")

    # Record source for all converted/installed skills
    if converted_files:
        for cf in converted_files:
            key = cf.name  # e.g. "mvp.md" or "mvp" (folder)
            record_source(dest_dir, key, source_label, source_type)
    elif source_path.exists():
        key = (skill_name or source_path.name)
        record_source(dest_dir, key, source_label, source_type)
    else:
        # Git install without conversion — record the imported dir
        key = dest.name
        record_source(dest_dir, key, source_label, source_type)

    # Show what was installed
    from ..skills import load_skills_from_dir
    installed = load_skills_from_dir(dest_dir)
    console.print(f"\n  Total skills in {'project' if project else 'global'}: {len(installed)}")


@app.command()
def remove(
    skill_name: str = typer.Argument(..., help="Skill ID or filename to remove (e.g. mvp, review.md)"),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Remove from a project instead of global"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Remove an installed skill.

    Examples:
      dotai remove mvp
      dotai remove mvp -p my-project
      dotai remove mvp --force
    """
    import shutil
    from ..store import load_config
    from ..skills import load_skills_from_dir, load_sources, save_sources

    config = load_config()

    if project:
        proj = config.get_project(project)
        if not proj:
            console.print(f"[red]Project '{project}' not found[/red]")
            raise typer.Exit(1)
        skills_dir = proj.skills_path
    else:
        skills_dir = config.global_skills_path

    # Find the skill by ID, filename, or directory name
    clean_name = skill_name.lstrip("/").removesuffix(".md")
    target: Path | None = None
    target_key: str | None = None

    # Check single-file skill
    md_path = skills_dir / f"{clean_name}.md"
    if md_path.exists():
        target = md_path
        target_key = md_path.name

    # Check folder-based skill
    dir_path = skills_dir / clean_name
    if not target and dir_path.is_dir() and (dir_path / "main.md").exists():
        target = dir_path
        target_key = dir_path.name

    # Search by skill ID across loaded skills
    if not target:
        all_skills = load_skills_from_dir(skills_dir)
        match = next((s for s in all_skills if s.id == clean_name), None)
        if match and match.file_path:
            if match.is_folder_skill and match.assets_dir:
                target = match.assets_dir
                target_key = match.assets_dir.name
            else:
                target = match.file_path
                target_key = match.file_path.name

    if not target or not target.exists():
        console.print(f"[red]Skill '{skill_name}' not found in {skills_dir}[/red]")
        raise typer.Exit(1)

    # Show what will be removed
    scope_label = f"project '{project}'" if project else "global"
    console.print(f"  [bold]Skill:[/bold] {clean_name}")
    console.print(f"  [bold]Path:[/bold] {target}")
    console.print(f"  [bold]Scope:[/bold] {scope_label}")

    # Check source
    sources = load_sources(skills_dir)
    src_info = sources.get(target_key or "", {})
    if src_info:
        console.print(f"  [bold]Source:[/bold] {src_info.get('url', '?')}")

    if not force:
        confirm = typer.confirm("Remove this skill?")
        if not confirm:
            console.print("[dim]Cancelled.[/dim]")
            raise typer.Exit(0)

    # Remove the file/directory
    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()

    # Clean up source manifest
    if target_key and target_key in sources:
        del sources[target_key]
        save_sources(skills_dir, sources)

    console.print(f"[green]Removed:[/green] {clean_name}")

    # Show remaining count
    remaining = load_skills_from_dir(skills_dir)
    console.print(f"  Total skills in {scope_label}: {len(remaining)}")


@app.command()
def new_skill(
    name: str = typer.Argument(..., help="Skill name"),
    trigger: Optional[str] = typer.Option(None, "--trigger", "-t", help="Slash command trigger"),
    role: Optional[str] = typer.Option(None, "--role", "-r", help="Role ID to use"),
    category: Optional[str] = typer.Option(None, "--category", "-c", help="Skill category"),
    folder: bool = typer.Option(False, "--folder", "-f", help="Create as folder-based skill with scripts/assets"),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Create in a project instead of global"),
):
    """Create a new skill from a template.

    Simple:  dotai new-skill "Deploy" -t /run_deploy -c deployment
    Folder:  dotai new-skill "Deploy" -t /run_deploy -c deployment --folder
    """
    from ..store import load_config
    from ..skills import create_skill_template, generate_skill_id

    config = load_config()

    if project:
        proj = config.get_project(project)
        if not proj:
            console.print(f"[red]Project '{project}' not found[/red]")
            raise typer.Exit(1)
        skills_dir = proj.skills_path
    else:
        skills_dir = config.global_skills_path

    skills_dir.mkdir(parents=True, exist_ok=True)
    skill_id = generate_skill_id(name)

    result = create_skill_template(name, trigger, role, category, folder)

    if isinstance(result, dict):
        # Folder-based skill
        skill_dir = skills_dir / skill_id
        skill_dir.mkdir(exist_ok=True)
        for filename, content in result.items():
            file_path = skill_dir / filename
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content)
        console.print(f"[green]Created folder skill:[/green] {skill_dir}/")
        console.print(f"  main.md, config.json, scripts/, assets/")
    else:
        # Single-file skill
        dest = skills_dir / f"{skill_id}.md"
        dest.write_text(result)
        console.print(f"[green]Created skill:[/green] {dest}")

    console.print(f"  Edit the skill to customize its behavior.")


def _import_plugin_legacy(
    source: str = typer.Argument(..., help="Path or git URL to a Claude plugin, Cursor plugin, or Gemini extension"),
    skill_name: Optional[str] = typer.Option(None, "--skill", "-s", help="Import only a specific skill by name"),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Install to a project instead of global"),
    include_agents: bool = typer.Option(False, "--include-agents", help="Also convert agents to dotai roles"),
    include_rules: bool = typer.Option(False, "--include-rules", help="Also convert Cursor .mdc rules to dotai rules"),
):
    """Import skills from a Claude plugin, Cursor plugin, or Gemini extension.

    Detects the plugin format automatically and converts all skills to dotai format.
    Also supports importing agents (as roles) and Cursor rules.

    Examples:
      dotai install /path/to/claude-plugin/
      dotai install /path/to/cursor-plugin/
      dotai install /path/to/gemini-extension/ -s my-skill
      dotai install https://github.com/user/claude-plugin
    """
    import shutil
    from ..converter import (
        detect_skill_format, convert_plugin_to_dotai, parse_plugin_manifest,
    )
    from ..skills import record_source
    from ..store import load_config

    config = load_config()

    if project:
        proj = config.get_project(project)
        if not proj:
            console.print(f"[red]Project '{project}' not found[/red]")
            raise typer.Exit(1)
        dest_dir = proj.skills_path
    else:
        dest_dir = config.global_skills_path

    dest_dir.mkdir(parents=True, exist_ok=True)

    # Resolve source: local path or git repo
    source_path = Path(source).expanduser().resolve()
    plugin_path: Path

    if source_path.exists():
        plugin_path = source_path
        source_label = str(source_path)
    else:
        # Git clone
        import subprocess
        import tempfile

        console.print(f"  [dim]Cloning {source}...[/dim]")
        tmp = Path(tempfile.mkdtemp())
        try:
            subprocess.run(
                ["git", "clone", "--depth", "1", source, str(tmp / "repo")],
                check=True, capture_output=True,
            )
            plugin_path = tmp / "repo"
            source_label = source
        except subprocess.CalledProcessError as e:
            console.print(f"[red]Failed to clone: {e.stderr.decode()[:200]}[/red]")
            raise typer.Exit(1)

    # Detect format
    fmt = detect_skill_format(plugin_path)
    if fmt not in ("claude-plugin", "cursor-plugin", "gemini-extension"):
        console.print(f"[red]Not a recognized plugin/extension format: {plugin_path}[/red]")
        console.print("  Expected one of:")
        console.print("    - .claude-plugin/plugin.json (Claude plugin)")
        console.print("    - .cursor-plugin/plugin.json (Cursor plugin)")
        console.print("    - gemini-extension.json (Gemini extension)")
        raise typer.Exit(1)

    # Show what we found
    manifest = parse_plugin_manifest(plugin_path)
    fmt_label = fmt.replace("-", " ").title()
    console.print(f"  [bold]{fmt_label}:[/bold] {manifest['name']}")
    if manifest["description"]:
        console.print(f"  [dim]{manifest['description'][:80]}[/dim]")
    console.print(f"  Skills: {len(manifest['skills'])}, Commands: {len(manifest['commands'])}, "
                  f"Agents: {len(manifest['agents'])}, Rules: {len(manifest['rules'])}")

    if manifest["has_hooks"]:
        console.print(f"  [yellow]Note: hooks found but cannot be converted to dotai[/yellow]")
    if manifest["has_mcp"]:
        console.print(f"  [yellow]Note: MCP server configs found but cannot be converted to dotai[/yellow]")

    # Convert
    results = convert_plugin_to_dotai(
        plugin_path, dest_dir,
        skill_filter=skill_name,
        include_agents=include_agents,
        include_rules=include_rules,
    )

    if not results:
        console.print("[yellow]No skills found to import.[/yellow]")
        raise typer.Exit(0)

    # Record sources
    for r in results:
        record_source(dest_dir, r.name, source_label, fmt)

    console.print(f"\n  [green]Imported {len(results)} item(s) to dotai format[/green]")
    for r in results:
        console.print(f"    {r}")

    # Show total count
    from ..skills import load_skills_from_dir
    scope_label = f"project '{project}'" if project else "global"
    installed = load_skills_from_dir(dest_dir)
    console.print(f"\n  Total skills in {scope_label}: {len(installed)}")


@app.command()
def vet(
    path: str = typer.Argument(..., help="Path to a skill file or directory to scan"),
):
    """Scan a skill for security risks before installing.

    Checks for RCE patterns, credential theft, data exfiltration,
    hardcoded secrets, defense evasion, and other malicious indicators.

    Examples:
      dotai vet ~/my-skills/deploy
      dotai vet ./SKILL.md
      dotai vet ~/.ai/skills/
    """
    from ..vet import vet_skill, format_report

    target = Path(path).expanduser().resolve()
    if not target.exists():
        console.print(f"[red]Path not found: {target}[/red]")
        raise typer.Exit(1)

    console.print(f"Scanning [bold]{target}[/bold] for security issues...\n")
    report = vet_skill(target)

    if report.is_clean:
        console.print("[green]No security issues found.[/green]")
    else:
        console.print(format_report(report))
        if report.should_block:
            console.print("[red bold]Audit recommends blocking this skill.[/red bold]")
            raise typer.Exit(1)
        elif report.should_warn:
            console.print("[yellow bold]Audit recommends review before using.[/yellow bold]")
