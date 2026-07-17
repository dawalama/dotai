"""dotai CLI — manage ~/.ai/ knowledge, roles, skills, and agent sync."""

import shutil
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from .. import __version__


def _version_callback(value: bool):
    if value:
        print(f"dotai {__version__}")
        raise typer.Exit()


app = typer.Typer(help="Portable engineering judgment for coding agents.", no_args_is_help=True)


@app.callback()
def main(
    version: bool = typer.Option(False, "--version", "-V", callback=_version_callback, is_eager=True, help="Show version and exit"),
):
    pass
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
    from ..store import get_config_dir, load_config, save_config
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
        (ai_dir / "preferences").mkdir(exist_ok=True)
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
        console.print(f"  Created: rules.md, roles/, skills/, preferences/, tools/")

        # Prepare context without silently taking ownership of team agent files.
        from ..sync import plan_sync, sync_local_context
        plan = plan_sync(project_path, get_config_dir())
        written = sync_local_context(plan, config, project_path.name)
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

        # Create rules, preferences, and tools dirs
        (ai_dir / "rules").mkdir(exist_ok=True)
        (ai_dir / "preferences").mkdir(exist_ok=True)
        (ai_dir / "tools").mkdir(exist_ok=True)

        # Create starter files
        if not (ai_dir / "rules.md").exists():
            (ai_dir / "rules.md").write_text(
                "# Global Rules\n\n"
                "Freeform, always-on notes that apply across every project. dotai inlines\n"
                "this file verbatim into resolved context, so keep it short and high-signal —\n"
                "every line here is spent on every task.\n\n"
                "Precedence: repository/team instructions > structured rules (`rules/*.md`) >\n"
                "this file > preference packs > model default. Don't restate what the model\n"
                "already does well (\"write clean code\", \"handle errors\"); capture only the\n"
                "conventions it would otherwise get wrong.\n\n"
                "For anything with a clear trigger — a file type, a design choice, a\n"
                "security boundary — prefer a structured rule so it loads only when relevant:\n\n"
                "    dotai learn \"title\" --directive \"what to do\"\n\n"
                "## Your rules\n\n"
                "<!-- Add durable, cross-project conventions below, then delete this line. -->\n"
            )
        console.print(f"[green]Initialized ~/.ai/[/green]")
        console.print(f"  {ai_dir}/rules.md")
        console.print(f"  {ai_dir}/roles/ ({len(list(roles_dir.glob('*.md')))} roles)")
        console.print(f"  {ai_dir}/skills/ ({len(list(skills_dir.glob('*.md')))} skills)")
        console.print(f"  {ai_dir}/preferences/")
        console.print(f"  {ai_dir}/tools/")
        console.print(f"\n[dim]Next: cd into a project and run `dotai sync` to prepare safe local context.[/dim]")
        console.print(f"[dim]Have an existing CLAUDE.md / AGENTS.md?  `dotai import-agent CLAUDE.md --dry-run`[/dim]")
        console.print(
            "[dim]Teach a rule:  `dotai learn \"title\" --directive \"what to do\" --dry-run`[/dim]"
        )
        console.print(f"[dim]Borrow style:  `dotai prefs new \"CLI\" --domain cli` then `dotai prefs use cli`[/dim]")


# Import submodules to register their commands with the app
from . import roles_cmd   # noqa: E402, F401
from . import skills_cmd  # noqa: E402, F401
from . import rules_cmd   # noqa: E402, F401
from . import prefs_cmd   # noqa: E402, F401
from . import sync_cmd    # noqa: E402, F401
from . import agents_cmd  # noqa: E402, F401
from . import insights_cmd  # noqa: E402, F401
