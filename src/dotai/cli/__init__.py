"""dotai CLI — manage ~/.ai/ knowledge, roles, skills, and agent sync."""

import shutil
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

app = typer.Typer(help="Universal AI context for any coding agent.", no_args_is_help=True)
console = Console()

SEED_DIR = Path(__file__).parent.parent / "seed"


@app.command()
def init(
    project: Optional[str] = typer.Argument(None, help="Project path to initialize (omit for global ~/.ai/)"),
    force: bool = typer.Option(False, "--force", "-f", help="Re-seed missing/updated roles and skills (overwrites seeds, keeps custom files)"),
):
    """Initialize ~/.ai/ with seed roles and skills, or add .ai/ to a project.

    Use --force to re-seed after upgrading dotai (overwrites seed files, keeps your custom files).
    """
    from ..store import load_config, save_config
    from ..models import ProjectConfig

    if project:
        # Project init
        project_path = Path(project).expanduser().resolve()
        if not project_path.exists():
            console.print(f"[red]Path does not exist: {project_path}[/red]")
            raise typer.Exit(1)

        ai_dir = project_path / ".ai"
        ai_dir.mkdir(exist_ok=True)
        (ai_dir / "rules").mkdir(exist_ok=True)
        (ai_dir / "roles").mkdir(exist_ok=True)
        (ai_dir / "skills").mkdir(exist_ok=True)
        (ai_dir / "tools").mkdir(exist_ok=True)

        # Create starter files
        if not (ai_dir / "rules.md").exists():
            (ai_dir / "rules.md").write_text(
                "# Project Rules\n\nProject-specific conventions and guidelines.\n"
            )
        # Register in config
        config = load_config()
        config.add_project(ProjectConfig(
            name=project_path.name,
            path=project_path,
        ))
        save_config(config)

        console.print(f"[green]Initialized .ai/ in {project_path}[/green]")
        console.print(f"  Created: rules.md, roles/, skills/, tools/")

        # Auto-sync agent config files into the project
        from ..sync import sync_project
        written = sync_project(project_path, config, project_path.name)
        for f in written:
            console.print(f"  [green]Synced[/green] {f}")
    else:
        # Global init
        ai_dir = Path.home() / ".ai"
        ai_dir.mkdir(exist_ok=True)

        # Copy seed roles
        roles_dir = ai_dir / "roles"
        roles_dir.mkdir(exist_ok=True)
        seed_roles = SEED_DIR / "roles"
        if seed_roles.exists():
            copied = 0
            for role_file in seed_roles.glob("*.md"):
                dest = roles_dir / role_file.name
                if force or not dest.exists():
                    shutil.copy2(role_file, dest)
                    copied += 1
            if copied:
                verb = "Updated" if force else "Seeded"
                console.print(f"  {verb} {copied} roles")

        # Copy seed skills (files and folders)
        skills_dir = ai_dir / "skills"
        skills_dir.mkdir(exist_ok=True)
        seed_skills = SEED_DIR / "skills"
        if seed_skills.exists():
            copied = 0
            # Single-file skills
            for skill_file in seed_skills.glob("*.md"):
                dest = skills_dir / skill_file.name
                if force or not dest.exists():
                    shutil.copy2(skill_file, dest)
                    copied += 1
            # Folder-based skills
            for item in seed_skills.iterdir():
                if item.is_dir() and (item / "main.md").exists():
                    dest = skills_dir / item.name
                    if force or not dest.exists():
                        if dest.exists():
                            shutil.rmtree(dest)
                        shutil.copytree(item, dest)
                        copied += 1
            if copied:
                verb = "Updated" if force else "Seeded"
                console.print(f"  {verb} {copied} skills")

        # Create rules and tools dirs
        (ai_dir / "rules").mkdir(exist_ok=True)
        (ai_dir / "tools").mkdir(exist_ok=True)

        # Create starter files
        if not (ai_dir / "rules.md").exists():
            (ai_dir / "rules.md").write_text(
                "# Global Rules\n\nUniversal AI coding rules across all projects.\n\n"
                "## Code Quality\n\n- Write clear, readable code\n- Handle errors explicitly\n"
                "- Prefer simple solutions over clever ones\n"
            )
        console.print(f"[green]Initialized ~/.ai/[/green]")
        console.print(f"  {ai_dir}/rules.md")
        console.print(f"  {ai_dir}/roles/ ({len(list(roles_dir.glob('*.md')))} roles)")
        console.print(f"  {ai_dir}/skills/ ({len(list(skills_dir.glob('*.md')))} skills)")
        console.print(f"  {ai_dir}/tools/")
        console.print(f"\n[dim]Next: cd into a project and run `dotai sync` to generate agent configs.[/dim]")


# Import submodules to register their commands with the app
from . import roles_cmd   # noqa: E402, F401
from . import skills_cmd  # noqa: E402, F401
from . import rules_cmd   # noqa: E402, F401
from . import sync_cmd    # noqa: E402, F401
from . import watch_cmd   # noqa: E402, F401
