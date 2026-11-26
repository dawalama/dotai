"""CLI command for harvesting candidate durable rules from native agent auto-memory."""

import json
from typing import Optional

import typer

from . import app, console


@app.command()
def harvest(
    source: str = typer.Argument("claude", help="Agent auto-memory source (currently: claude)"),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Filter by project directory substring"),
    all_items: bool = typer.Option(False, "--all", "-a", help="Include items already covered by ~/.ai/rules/"),
    promote: Optional[int] = typer.Option(None, "--promote", help="Promote candidate #N (1-based) into ~/.ai/rules/"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview promotion without writing"),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON"),
):
    """Inspect native agent auto-memory and promote durable lessons into ~/.ai/rules/."""
    from ..harvest import SUPPORTED_HARVEST_SOURCES, harvest_claude_memory
    from ..rules import build_rule_from_directive, create_rule_from_directive
    from ..store import load_config

    source = source.lower()
    if source not in SUPPORTED_HARVEST_SOURCES:
        console.print(f"[red]Unsupported harvest source: {source}. Supported: {', '.join(SUPPORTED_HARVEST_SOURCES)}[/red]")
        raise typer.Exit(2)

    config = load_config()
    candidates = harvest_claude_memory(
        config,
        project_filter=project,
        include_existing=all_items,
    )

    if promote is not None:
        if promote < 1 or promote > len(candidates):
            console.print(f"[red]Candidate #{promote} out of range (found {len(candidates)}).[/red]")
            raise typer.Exit(2)
        chosen = candidates[promote - 1]
        if dry_run:
            dest, _ = build_rule_from_directive(
                name=chosen.title,
                dest_dir=config.global_rules_path,
                directive=chosen.body,
                tags=["harvested", chosen.source],
            )
            console.print(f"[bold]Dry run[/bold] — would create {dest}:")
            console.print(f"  Title: {chosen.title}")
            console.print(f"  Body: {chosen.body}")
            return
        path = create_rule_from_directive(
            name=chosen.title,
            dest_dir=config.global_rules_path,
            directive=chosen.body,
            tags=["harvested", chosen.source],
        )
        console.print(f"[green]Promoted candidate #{promote} to {path}[/green]")
        console.print("[dim]Run `dotai agent setup all --apply` to project it into your coding agents.[/dim]")
        return

    if json_output:
        console.print_json(json.dumps([c.to_dict() for c in candidates], indent=2))
        return

    if not candidates:
        console.print(f"[dim]No new candidate lessons found in {source} auto-memory.[/dim]")
        return

    console.print(f"[bold]Harvest candidates ({source})[/bold] · {len(candidates)} item(s)\n")
    for idx, c in enumerate(candidates, 1):
        status = " [dim](already in dotai)[/dim]" if c.already_in_dotai else ""
        console.print(f"  [cyan]#{idx}[/cyan] [bold]{c.title}[/bold] [{c.memory_type} · {c.project_hint}]{status}")
        preview = c.body.replace("\n", " ")
        if len(preview) > 120:
            preview = preview[:117] + "..."
        console.print(f"      {preview}")
        console.print(f"      [dim]{c.source_path}[/dim]")
    console.print(
        "\n[dim]Promote a lesson: `dotai harvest claude --promote <N> --dry-run` (omit --dry-run to save).[/dim]"
    )
