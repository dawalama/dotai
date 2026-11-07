"""CLI commands for lossless migration of legacy skills and roles."""

from pathlib import Path
from typing import Optional

import typer
from rich.table import Table

from . import app, console


@app.command()
def migrate(
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Scope to a specific project"),
    dry_run: bool = typer.Option(False, "--dry-run", "--check", help="Preview migration without modifying files"),
    skills_only: bool = typer.Option(False, "--skills", help="Migrate legacy skills only"),
    roles_only: bool = typer.Option(False, "--roles", help="Migrate legacy roles only"),
):
    """Losslessly migrate legacy folder skills and roles to canonical native packages.

    Converts folder skills (main.md -> SKILL.md) and retires legacy persona roles
    into user-authored perspective skills. Creates backups before making changes.
    """
    from ..store import get_config_dir, load_config
    from ..migration import apply_migration, plan_migration

    config = load_config()
    include_skills = not roles_only
    include_roles = not skills_only

    plan = plan_migration(
        config,
        project_name=project,
        include_skills=include_skills,
        include_roles=include_roles,
    )

    if not plan.actions:
        console.print("[green]No legacy skills or roles found to migrate.[/green]")
        return

    table = Table(title=f"Planned Migrations ({plan.scope})")
    table.add_column("Kind", style="bold")
    table.add_column("Action", style="cyan")
    table.add_column("Source", style="dim")
    table.add_column("Target", style="green")
    table.add_column("Warnings", style="yellow")

    for action in plan.actions:
        table.add_row(
            action.kind,
            action.action,
            str(action.source_path),
            str(action.target_path),
            "; ".join(action.warnings),
        )

    console.print(table)

    if dry_run:
        console.print(f"\n[dim]Dry-run: {len(plan.actions)} action(s) previewed. No files changed.[/dim]")
        return

    backup_root = get_config_dir() / "backups"
    applied = apply_migration(plan, backup_root=backup_root)
    console.print(f"\n[green]Successfully migrated {len(applied)} item(s).[/green]")
    if applied and applied[0].backup_path:
        console.print(f"[dim]Backups created in: {applied[0].backup_path.parent}[/dim]")
