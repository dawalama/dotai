"""CLI commands for safe local sync, context resolution, primer, and search."""

import json
from pathlib import Path
from typing import Optional

import typer
from rich.table import Table

from . import app, console


@app.command()
def sync(
    path: str = typer.Argument(".", help="Project path to prepare context for"),
    check: bool = typer.Option(False, "--check", help="Show the local target without writing"),
):
    """Prepare repository-safe local context outside the worktree."""
    from ..store import get_config_dir, load_config
    from ..sync import plan_sync, sync_local_context

    config = load_config()
    project_path = Path(path).expanduser().resolve()

    # Find project name
    project_config = next((p for p in config.projects if p.path == project_path), None)
    project_name = project_config.name if project_config else None

    plan = plan_sync(project_path, get_config_dir())

    console.print(f"Mode: [bold]{plan.mode}[/bold]")
    console.print(f"Project: {plan.project_path}")
    console.print(f"Target: {plan.target_path}")
    console.print("[dim]Team agent files remain untouched; team instructions take precedence.[/dim]")
    console.print("[dim]Use `dotai primer --path .` or an agent adapter to load this context.[/dim]")
    if check:
        return

    written = sync_local_context(plan, config, project_name)

    for f in written:
        console.print(f"  [green]Synced[/green] {f}")


@app.command()
def primer(
    project: Optional[str] = typer.Option(None, help="Scope to a specific project"),
    path: Optional[str] = typer.Option(None, "--path", help="Resolve project context from this path"),
):
    """Print a compact agent primer for tools without an adapter."""
    from ..store import load_config
    from ..sync import generate_primer

    config = load_config()
    project_path = Path(path).expanduser().resolve() if path else None
    if project_path:
        matched = next((p for p in config.projects if p.path == project_path), None)
        if matched:
            project = matched.name
    typer.echo(generate_primer(
        config, project, project_path=project_path,
        compact=True,
    ))


@app.command("context")
def resolve_task_context(
    path: str = typer.Option(".", "--path", help="Project path used for scoped context"),
    task: str = typer.Option("", "--task", help="Current task; routes only unambiguous skill aliases"),
    files: Optional[str] = typer.Option(None, "--files", help="Comma-separated affected file paths"),
    contexts: Optional[str] = typer.Option(None, "--context", help="Comma-separated explicit contexts/tags"),
    domains: Optional[str] = typer.Option(None, "--domain", help="Comma-separated active preference domains to load"),
    skill: Optional[str] = typer.Option(None, "--skill", help="Skill id, name, or trigger to load fully"),
    role: Optional[str] = typer.Option(None, "--role", help="Role id or name to load fully"),
    rules: Optional[str] = typer.Option(None, "--rule", help="Comma-separated rule ids to load fully"),
    with_prefs: Optional[str] = typer.Option(None, "--with-prefs", help="Session preference pack overlay ids"),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON"),
    agent: Optional[str] = typer.Option(
        None, "--agent", help="Record a local invocation receipt for an adapter", hidden=True
    ),
):
    """Resolve only the rules, preferences, skill, and role needed for a task."""
    from ..context import resolve_context, save_resolution_receipt
    from ..store import get_config_dir, load_config

    def split(raw: Optional[str]) -> list[str]:
        return [value.strip() for value in raw.split(",") if value.strip()] if raw else []

    config = load_config()
    project_path = Path(path).expanduser().resolve()
    matched = next((p for p in config.projects if p.path == project_path), None)
    project_name = matched.name if matched else None
    try:
        resolved = resolve_context(
            config,
            project_path,
            project_name,
            task=task,
            files=split(files),
            contexts=split(contexts),
            domains=split(domains),
            skill_id=skill,
            role_id=role,
            rule_ids=split(rules),
            extra_prefs=split(with_prefs),
        )
    except ValueError as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(2) from error

    if agent:
        try:
            save_resolution_receipt(
                resolved, agent, get_config_dir() / "receipts"
            )
        except (ValueError, OSError) as error:
            typer.echo(
                f"Warning: context resolved, but receipt was not saved: {error}",
                err=True,
            )

    if json_output:
        typer.echo(json.dumps(resolved.to_dict(), indent=2))
    else:
        typer.echo(resolved.to_prompt(), nl=False)


@app.command()
def search(
    query: str = typer.Argument("", help="Search keyword (optional if using --tag)"),
    type: Optional[str] = typer.Option(None, "--type", "-t", help="Filter by rule, preference, role, or skill"),
    tag: Optional[str] = typer.Option(None, "--tag", help="Filter by tag"),
):
    """Search live dotai knowledge by keyword, type, or tag.

    Examples:
      dotai search "useEffect"
      dotai search "review" --type skill
      dotai search --tag security
      dotai search "auth" --type rule --tag react
    """
    from ..preferences import load_all_preferences
    from ..roles import load_all_roles
    from ..rules import load_all_rules
    from ..skills import load_all_skills
    from ..store import load_config

    valid_types = {"rule", "preference", "role", "skill"}
    kind = type.strip().lower() if type else None
    if kind and kind not in valid_types:
        console.print(f"[red]Unknown type: {type}[/red]")
        console.print("Valid types: rule, preference, role, skill")
        raise typer.Exit(1)

    config = load_config()
    items = []
    items.extend(("rule", item.id, item.description, item.tags, item.file_path) for item in load_all_rules(config))
    items.extend(("preference", item.id, item.description, item.tags, item.file_path) for item in load_all_preferences(config))
    items.extend(("role", item.id, item.description, item.tags, item.file_path) for item in load_all_roles(config))
    items.extend(("skill", item.id, item.description, item.tags, item.file_path) for item in load_all_skills(config))

    query_lower = query.strip().lower()
    tag_lower = tag.strip().lower() if tag else None
    results = [
        item for item in items
        if (not kind or item[0] == kind)
        and (not query_lower or query_lower in " ".join((item[1], item[2], *item[3])).lower())
        and (not tag_lower or tag_lower in {value.lower() for value in item[3]})
    ]

    if not results:
        console.print("[dim]No results found.[/dim]")
        return

    # Display results
    table = Table(title=f"Search: {query or '*'}")
    table.add_column("Type", style="magenta")
    table.add_column("Name", style="bold")
    table.add_column("Tags", style="dim")
    table.add_column("Summary")
    table.add_column("File", style="dim")

    for item_type, name, summary, tags, file_path in results:
        file_str = ""
        if file_path:
            p = str(file_path)
            home = str(Path.home())
            if p.startswith(home):
                p = "~" + p[len(home):]
            file_str = p

        table.add_row(
            item_type,
            name,
            ", ".join(tags),
            summary[:60],
            file_str,
        )

    console.print(table)
    console.print(f"\n[dim]{len(results)} result(s)[/dim]")
