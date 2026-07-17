"""CLI for deterministic local usage insights."""

import json
from pathlib import Path
from typing import Optional

import typer
from rich.table import Table

from . import app, console


@app.command()
def insights(
    agent: Optional[str] = typer.Option(None, "--agent", help="Filter to one adapter agent"),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Filter to a registered project"),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON"),
):
    """Show local, factual signals about which judgment dotai resolved."""
    from ..insights import build_insights
    from ..store import get_config_dir, load_config

    config = load_config()
    project_path: Path | None = None
    if project:
        matched = config.get_project(project)
        if not matched:
            console.print(f"[red]Project '{project}' not found[/red]")
            raise typer.Exit(2)
        project_path = matched.path

    try:
        report = build_insights(
            config,
            get_config_dir() / "receipts",
            agent=agent.strip().lower() if agent else None,
            project_path=project_path,
        )
    except ValueError as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(2) from error
    if json_output:
        typer.echo(json.dumps(report.to_dict(), indent=2))
        return

    console.print("dotai insights · local receipt metadata")
    console.print(
        f"  Resolutions: {report.resolutions} · complete {report.complete} · "
        f"provisional {report.provisional}"
    )
    if report.first_resolution:
        console.print(f"  Window: {report.first_resolution} → {report.last_resolution}")
    if report.agents:
        console.print(f"  Agents: {', '.join(report.agents)}")
    if not report.resolutions:
        console.print("\n[yellow]No resolution history recorded yet.[/yellow]")
        console.print("Use a configured adapter or `dotai context --agent <name>`.")
        return

    table = Table(title="Resolved judgment")
    table.add_column("Kind", style="magenta")
    table.add_column("Item", style="bold")
    table.add_column("Selected", justify="right")
    table.add_column("Summary exposure", justify="right")
    table.add_column("Last selected", style="dim")
    for item in report.items:
        table.add_row(
            item.kind,
            item.item_id,
            str(item.selected),
            str(item.exposed) if item.kind == "rule" else "—",
            item.last_selected or "never",
        )
    console.print(table)

    unused_count = sum(len(ids) for ids in report.unused.values())
    console.print(f"\nKnown items never selected in this window: {unused_count}")
    for kind, ids in report.unused.items():
        if ids:
            preview = ", ".join(ids[:8])
            suffix = f" (+{len(ids) - 8} more)" if len(ids) > 8 else ""
            console.print(f"  {kind}: {preview}{suffix}")
    console.print(
        "\n[dim]Selection is evidence of delivery, not proof that the agent followed the instruction.[/dim]"
    )
