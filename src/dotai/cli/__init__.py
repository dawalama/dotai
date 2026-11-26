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


@app.command()
def init(
    project: Optional[str] = typer.Argument(None, help="Project path to initialize (omit for global ~/.ai/)"),
    force: bool = typer.Option(False, "--force", "-f", help="Re-initialize starter files if missing"),
):
    """Initialize ~/.ai/ knowledge directories, or add .ai/ to a project."""
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
        (ai_dir / "skills").mkdir(exist_ok=True)
        (ai_dir / "preferences").mkdir(exist_ok=True)

        # Create starter files
        if not (ai_dir / "rules.md").exists() or force:
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
        console.print(f"  Created: rules.md, rules/, skills/, preferences/")

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
        (ai_dir / "rules").mkdir(exist_ok=True)
        (ai_dir / "skills").mkdir(exist_ok=True)
        (ai_dir / "preferences").mkdir(exist_ok=True)

        # Create starter files
        if not (ai_dir / "rules.md").exists() or force:
            (ai_dir / "rules.md").write_text(
                "# Global Rules\n\n"
                "Freeform, always-on notes that apply across every project. Keep this short\n"
                "and high-signal — every line here is loaded on every task.\n\n"
                "Precedence: repository/team instructions > structured rules (`rules/*.md`) >\n"
                "this file > preference packs > model default. Don't restate what the model\n"
                "already does well (\"write clean code\", \"handle errors\"); capture only the\n"
                "conventions it would otherwise get wrong.\n\n"
                "For anything scoped to specific files, prefer a structured rule with globs:\n\n"
                "    dotai learn \"title\" --directive \"what to do\" --globs \"*.tsx,*.ts\"\n\n"
                "## Your rules\n\n"
                "<!-- Add durable, cross-project conventions below, then delete this line. -->\n"
            )
        console.print(f"[green]Initialized ~/.ai/[/green]")
        console.print(f"  {ai_dir}/rules.md")
        console.print(f"  {ai_dir}/rules/")
        console.print(f"  {ai_dir}/skills/")
        console.print(f"  {ai_dir}/preferences/")
        console.print(f"\n[dim]Next: project your personal guidance into your coding agents:[/dim]")
        console.print(f"[dim]  `dotai agent setup claude --apply` (or `codex`, `gemini`, `agents`, `all`)[/dim]")
        console.print(f"[dim]Harvest lessons from Claude auto-memory: `dotai harvest claude`[/dim]")
        console.print(
            "[dim]Teach a rule:  `dotai learn \"title\" --directive \"what to do\" --dry-run`[/dim]"
        )


@app.command()
def trust(
    path: Optional[str] = typer.Argument(None, help="Directory or repository path to trust for local .ai/ loading"),
    remove: bool = typer.Option(False, "--remove", "-r", help="Remove path from the trust list"),
    list_all: bool = typer.Option(False, "--list", "-l", help="List trusted paths and strict-trust setting"),
    strict: Optional[str] = typer.Option(None, "--strict", help="Require explicit trust for repo .ai/ dirs: on or off"),
):
    """Manage trusted repository paths to guard against untrusted .ai/ instruction poisoning."""
    from ..store import load_config, save_config

    config = load_config()
    changed = False

    if strict is not None:
        val = strict.strip().lower()
        if val not in ("on", "off"):
            console.print("[red]--strict must be 'on' or 'off'[/red]")
            raise typer.Exit(2)
        config.require_trust = val == "on"
        changed = True
        console.print(f"Strict trust mode: [bold]{val}[/bold]")

    if path:
        target = Path(path).expanduser().resolve()
        if remove:
            if config.untrust_path(target):
                changed = True
                console.print(f"[green]Removed trust for {target}[/green]")
            else:
                console.print(f"[yellow]{target} was not in trusted_paths[/yellow]")
        else:
            trusted = config.trust_path(target)
            changed = True
            console.print(f"[green]Trusted {trusted}[/green]")

    if changed:
        save_config(config)

    if list_all or (not path and strict is None):
        console.print(f"Strict trust mode: [bold]{'on' if config.require_trust else 'off'}[/bold]")
        if config.trusted_paths:
            console.print("Trusted paths:")
            for entry in config.trusted_paths:
                console.print(f"  - {entry}")
        else:
            console.print("[dim]No explicit trusted paths (registered projects are implicitly trusted).[/dim]")


# Import submodules to register their commands with the app
from . import roles_cmd   # noqa: E402, F401
from . import skills_cmd  # noqa: E402, F401
from . import rules_cmd   # noqa: E402, F401
from . import prefs_cmd   # noqa: E402, F401
from . import sync_cmd    # noqa: E402, F401
from . import agents_cmd  # noqa: E402, F401
from . import insights_cmd  # noqa: E402, F401
from . import migrate_cmd  # noqa: E402, F401
from . import harvest_cmd  # noqa: E402, F401
