"""CLI commands for roles."""

from typing import Optional

import typer
from rich.table import Table

from . import app, console


@app.command()
def roles():
    """List all available roles."""
    from ..store import load_config
    from ..roles import load_all_roles

    config = load_config()
    all_roles = load_all_roles(config)

    if not all_roles:
        console.print("[dim]No roles found. Run `dotai init` to seed default roles.[/dim]")
        return

    table = Table(title="Available Roles")
    table.add_column("Name", style="bold")
    table.add_column("Scope", style="dim")
    table.add_column("Description")
    table.add_column("Tags", style="dim")

    for role in all_roles:
        table.add_row(role.id, role.scope, role.description[:60], ", ".join(role.tags))

    console.print(table)


@app.command()
def role(
    name: str = typer.Argument(..., help="Role ID to output (e.g. qa, paranoid-reviewer, debugger)"),
):
    """Output a role's full prompt to stdout.

    Use this to inject a persona into any agent:
      dotai role qa | pbcopy
      dotai role paranoid-reviewer > /tmp/role.md
    """
    from ..store import load_config
    from ..roles import load_all_roles

    config = load_config()
    all_roles = load_all_roles(config)

    matched = next((r for r in all_roles if r.id == name), None)

    if not matched:
        console.print(f"[red]Role '{name}' not found.[/red]")
        console.print("Available roles:")
        for r in all_roles:
            console.print(f"  {r.id}: {r.description[:60]}")
        raise typer.Exit(1)

    # print() intentional — stdout for piping, no Rich markup
    print(matched.to_prompt())
