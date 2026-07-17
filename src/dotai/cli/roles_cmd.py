"""CLI commands for roles."""

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
