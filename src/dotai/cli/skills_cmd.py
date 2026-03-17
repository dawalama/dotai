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
    table.add_column("Type", style="dim")
    table.add_column("Description")

    for skill in all_skills:
        skill_type = "📁" if skill.is_folder_skill else "📄"
        table.add_row(
            skill.id,
            skill.trigger or "",
            skill.category.value if skill.category else "",
            skill.role or "",
            skill.scope,
            skill_type,
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

    # Show what was installed
    from ..skills import load_skills_from_dir
    installed = load_skills_from_dir(dest_dir)
    console.print(f"\n  Total skills in {'project' if project else 'global'}: {len(installed)}")


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
