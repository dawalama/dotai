"""CLI commands for skills."""

from pathlib import Path
from typing import Optional

import typer
from rich.table import Table

from . import app, console


@app.command()
def prompt(
    skill_name: str = typer.Argument(..., help="Skill ID or trigger (e.g. review, /commit)"),
    role_override: Optional[str] = typer.Option(None, "--role", "-r", help="Role to adopt (overrides skill's default role)"),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Scope to a project"),
):
    """Assemble a complete prompt from a skill + role, ready for any agent.

    The skill's steps and the role's persona are composed into a single
    prompt that can be piped into any AI agent.

    Examples:
      dotai prompt review --role qa
      dotai prompt review --role paranoid-reviewer
      dotai prompt commit
      dotai prompt review --role qa | pbcopy
    """
    from ..store import load_config
    from ..roles import load_all_roles
    from ..skills import load_all_skills

    config = load_config()
    all_skills = load_all_skills(config)
    all_roles = load_all_roles(config)

    # Filter by project if specified
    if project:
        all_skills = [s for s in all_skills if s.scope == project or s.scope == "global"]
        all_roles = [r for r in all_roles if r.scope == project or r.scope == "global"]

    # Find skill by exact ID or trigger
    clean_name = skill_name.lstrip("/")
    skill = next((s for s in all_skills if s.id == clean_name), None)
    if not skill:
        skill = next((s for s in all_skills if s.trigger and s.trigger.lstrip("/") == clean_name), None)

    if not skill:
        console.print(f"[red]Skill '{skill_name}' not found.[/red]")
        console.print("Available skills:")
        for s in all_skills:
            trigger = f" ({s.trigger})" if s.trigger else ""
            console.print(f"  {s.id}{trigger}: {s.description[:50]}")
        raise typer.Exit(1)

    # Resolve role: explicit override > skill's default > none
    role_id = role_override or skill.role
    resolved_role = None
    if role_id:
        resolved_role = next((r for r in all_roles if r.id == role_id), None)
        if not resolved_role:
            console.print(f"[red]Role '{role_id}' not found.[/red]")
            console.print("Available roles:")
            for r in all_roles:
                console.print(f"  {r.id}: {r.description[:60]}")
            raise typer.Exit(1)

    # print() intentional — stdout for piping, no Rich markup
    print(skill.to_prompt(resolved_role=resolved_role))


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
    source: str = typer.Argument(..., help="Git repo URL or local path to install skill(s) from"),
    skill_name: Optional[str] = typer.Option(None, "--skill", "-s", help="Specific skill name within the repo"),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Install to a project instead of global"),
):
    """Install skills from a git repo or local directory.

    From a git repo:
      dotai install https://github.com/user/ai-skills
      dotai install https://github.com/user/ai-skills -s deploy

    From a local directory:
      dotai install ~/my-skills/review
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

    source_path = Path(source).expanduser()
    if source_path.exists():
        # Local install
        dest_name = skill_name or source_path.name
        dest = dest_dir / dest_name

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

    # Auto-detect and convert Claude-native skills
    from ..converter import detect_skill_format, convert_claude_to_dotai
    from ..skills import record_source

    # Determine source label for tracking
    source_label = source if not source_path.exists() else str(source_path)
    source_type = "local" if source_path.exists() else "git"

    # Check if we just installed Claude-native skill(s)
    installed_path = dest_dir / (skill_name or source_path.name) if source_path.exists() else dest
    converted_files: list[Path] = []

    if installed_path.exists():
        fmt = detect_skill_format(installed_path)
        if fmt == "claude-native":
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
def convert(
    source: str = typer.Argument(..., help="Path to Claude-native SKILL.md file or directory"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output directory (default: global skills dir)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be converted without writing"),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Install converted skill to a project"),
):
    """Convert a Claude-native SKILL.md to dotai format.

    Examples:
      dotai convert /path/to/SKILL.md
      dotai convert /path/to/skill-dir/ --dry-run
      dotai convert /path/to/SKILL.md -o ~/my-skills/
    """
    from ..converter import detect_skill_format, convert_claude_to_dotai
    from ..store import load_config

    source_path = Path(source).expanduser().resolve()
    if not source_path.exists():
        console.print(f"[red]Source not found: {source_path}[/red]")
        raise typer.Exit(1)

    fmt = detect_skill_format(source_path)
    if fmt == "dotai":
        console.print(f"[yellow]Already in dotai format: {source_path}[/yellow]")
        raise typer.Exit(0)
    if fmt == "unknown":
        console.print(f"[yellow]Unknown format (will attempt conversion): {source_path}[/yellow]")

    if dry_run:
        from ..converter import parse_claude_skill_md, _detect_structure_in_body
        parsed = parse_claude_skill_md(source_path)
        detected = _detect_structure_in_body(parsed["body"])
        console.print(f"[bold]Source:[/bold] {source_path}")
        console.print(f"[bold]Format:[/bold] {fmt}")
        console.print(f"[bold]Name:[/bold] {parsed['frontmatter'].get('name', source_path.stem)}")
        console.print(f"[bold]Description:[/bold] {parsed['frontmatter'].get('description', detected['description'][:80])}")
        console.print(f"[bold]Structured:[/bold] {detected['is_structured']}")
        console.print(f"[bold]Steps:[/bold] {len(detected['steps'])}")
        console.print(f"[bold]Inputs:[/bold] {len(detected['inputs'])}")
        console.print(f"[bold]Examples:[/bold] {len(detected['examples'])}")
        console.print(f"[bold]Has scripts/:[/bold] {parsed['has_scripts']}")
        console.print(f"[bold]Has assets/:[/bold] {parsed['has_assets']}")
        return

    # Determine destination
    if output:
        dest_dir = Path(output).expanduser().resolve()
    elif project:
        config = load_config()
        proj = config.get_project(project)
        if not proj:
            console.print(f"[red]Project '{project}' not found[/red]")
            raise typer.Exit(1)
        dest_dir = proj.skills_path
    else:
        config = load_config()
        dest_dir = config.global_skills_path

    result = convert_claude_to_dotai(source_path, dest_dir)
    console.print(f"[green]Converted:[/green] {source_path.name} -> {result}")


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
