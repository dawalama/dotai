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
        console.print("[dim]No legacy roles found. (Roles are retired as an automatic abstraction; use native skills instead.)[/dim]")
        return

    table = Table(title="Available Roles (Transitional)")
    table.add_column("Name", style="bold")
    table.add_column("Scope", style="dim")
    table.add_column("Description")
    table.add_column("Tags", style="dim")

    for role in all_roles:
        table.add_row(role.id, role.scope, role.description[:60], ", ".join(role.tags))

    console.print(table)
    console.print("[yellow]Notice: Roles are retired as an automatic persona abstraction. Run `dotai migrate` to migrate existing roles to user-authored skills.[/yellow]")
