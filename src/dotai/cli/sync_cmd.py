"""CLI commands for sync, context, primer, index, tree, and search."""

import json
from pathlib import Path
from typing import Optional

import typer
from rich.table import Table

from . import app, console


@app.command()
def sync(
    path: str = typer.Argument(".", help="Project path to sync into"),
    agents: Optional[str] = typer.Option(None, help="Comma-separated: claude,cursor,gemini,generic"),
    full: bool = typer.Option(
        False,
        "--full",
        help="Inline full role personas and skill definitions (larger context; default is catalog + full rules)",
    ),
    with_prefs: Optional[str] = typer.Option(
        None,
        "--with-prefs",
        help="Comma-separated preference pack ids to activate for this sync only (session overlay)",
    ),
    local: bool = typer.Option(False, "--local", help="Write personal context outside the repository"),
    shared: bool = typer.Option(False, "--shared", help="Explicitly update repository agent files"),
    check: bool = typer.Option(False, "--check", help="Show the resolved mode and paths without writing"),
):
    """Prepare ~/.ai/ knowledge for coding agents.

    Git repositories default to local context stored outside the worktree.
    Use --shared only when the team intends to update repository agent files.
    """
    from ..store import get_config_dir, load_config
    from ..sync import plan_sync, sync_local_context, sync_project

    if local and shared:
        console.print("[red]Choose either --local or --shared, not both.[/red]")
        raise typer.Exit(2)

    config = load_config()
    project_path = Path(path).expanduser().resolve()

    # Find project name
    project_config = next((p for p in config.projects if p.path == project_path), None)
    project_name = project_config.name if project_config else None

    agent_list = [a.strip() for a in agents.split(",") if a.strip()] if agents else None
    extra = [p.strip() for p in with_prefs.split(",")] if with_prefs else None
    requested_mode = "local" if local else "shared" if shared else "auto"
    try:
        plan = plan_sync(project_path, get_config_dir(), agent_list, requested_mode)
    except ValueError as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(2) from error

    console.print(f"Mode: [bold]{plan.mode}[/bold]")
    console.print(f"Project: {plan.project_path}")
    console.print(f"Target: {plan.target_path}")
    if plan.mode == "local":
        console.print("[dim]Team agent files remain untouched; team instructions take precedence.[/dim]")
        console.print("[dim]Use `dotai primer --path .` or an agent adapter to load this context.[/dim]")
    else:
        console.print("[yellow]Shared mode updates repository-owned agent files.[/yellow]")
    if check:
        return

    if plan.mode == "local":
        written = sync_local_context(
            plan, config, project_name, full=full, extra_prefs=extra
        )
    else:
        written = sync_project(
            project_path, config, project_name, plan.agents, full=full, extra_prefs=extra
        )

    for f in written:
        console.print(f"  [green]Synced[/green] {f}")


@app.command()
def detach(
    path: str = typer.Argument(".", help="Repository path to detach from dotai shared sync"),
    apply: bool = typer.Option(False, "--apply", help="Back up and apply the displayed cleanup"),
):
    """Remove old shared-sync artifacts once; preview by default.

    Only marker-delimited dotai blocks and dotai-marked Claude skills are
    eligible. Team-authored and unmarked content is never removed.
    """
    from ..store import get_config_dir
    from ..sync import apply_detach, plan_detach

    project_path = Path(path).expanduser().resolve()
    actions = plan_detach(project_path)
    console.print(f"Detach plan · {project_path}")
    if not actions:
        console.print("[green]No dotai-managed repository artifacts found.[/green]")
        return

    for action in actions:
        verb = "UPDATE" if action.action == "update" else "DELETE"
        console.print(f"  [yellow]{verb}[/yellow] {action.kind} · {action.path}")

    if not apply:
        console.print(
            "\n[dim]Preview only. Run `dotai detach --apply` to back up and apply this plan.[/dim]"
        )
        return

    changed, backup_dir = apply_detach(
        actions, get_config_dir() / "backups" / "detach"
    )
    console.print(f"\n[green]Detached {len(changed)} artifact(s).[/green]")
    console.print(f"Backup: {backup_dir}")


@app.command()
def primer(
    project: Optional[str] = typer.Option(None, help="Scope to a specific project"),
    path: Optional[str] = typer.Option(None, "--path", help="Resolve project context from this path"),
    full: bool = typer.Option(False, "--full", help="Include full role personas and skill definitions"),
    with_prefs: Optional[str] = typer.Option(
        None,
        "--with-prefs",
        help="Comma-separated preference pack ids to include for this primer only",
    ),
):
    """Print the agent primer to stdout (for piping into other tools)."""
    from ..store import load_config
    from ..sync import generate_primer

    config = load_config()
    project_path = Path(path).expanduser().resolve() if path else None
    if project_path:
        matched = next((p for p in config.projects if p.path == project_path), None)
        if matched:
            project = matched.name
    extra = [p.strip() for p in with_prefs.split(",")] if with_prefs else None
    typer.echo(generate_primer(
        config, project, project_path=project_path,
        compact=not full, full=full, extra_prefs=extra,
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
def index(
    refresh: bool = typer.Option(False, "--refresh", "-r", help="Force rebuild"),
):
    """Build the knowledge index."""
    from ..store import load_config, save_index, load_index
    from ..indexer import build_full_index

    if not refresh:
        existing = load_index()
        if existing:
            console.print(existing.to_toc())
            return

    config = load_config()
    idx = build_full_index(config)
    save_index(idx)
    console.print(idx.to_toc())
    console.print(f"\n[green]Index saved[/green]")


@app.command()
def tree():
    """Show the knowledge tree."""
    from ..store import load_index

    idx = load_index()
    if not idx:
        console.print("[dim]No index found. Run `dotai index --refresh` first.[/dim]")
        return

    console.print(idx.to_toc())


@app.command()
def search(
    query: str = typer.Argument("", help="Search keyword (optional if using --tag)"),
    type: Optional[str] = typer.Option(None, "--type", "-t", help="Filter by node type (rule, role, skill, document, section)"),
    tag: Optional[str] = typer.Option(None, "--tag", help="Filter by tag"),
):
    """Search the knowledge index by keyword, type, or tag.

    Examples:
      dotai search "useEffect"
      dotai search "review" --type skill
      dotai search --tag security
      dotai search "auth" --type rule --tag react
    """
    from ..store import load_index, load_config, save_index
    from ..models import NodeType
    from ..indexer import build_full_index

    idx = load_index()
    if not idx:
        # Auto-build index if missing
        config = load_config()
        idx = build_full_index(config)
        save_index(idx)

    # Start with all nodes matching the text query (or all leaf nodes if no query)
    if query:
        results = idx.find_by_text(query)
    else:
        results = _flatten(idx)

    # Filter by type
    if type:
        node_type = _resolve_node_type(type)
        if not node_type:
            console.print(f"[red]Unknown type: {type}[/red]")
            console.print("Valid types: rule, role, skill, document, section, tool, project, category")
            raise typer.Exit(1)
        results = [r for r in results if r.node_type == node_type]

    # Filter by tag
    if tag:
        tag_lower = tag.lower()
        results = [r for r in results if tag_lower in [t.lower() for t in r.tags]]

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

    for node in results:
        file_str = ""
        if node.file_path:
            p = str(node.file_path)
            home = str(Path.home())
            if p.startswith(home):
                p = "~" + p[len(home):]
            file_str = p

        table.add_row(
            node.node_type.value,
            node.name,
            ", ".join(node.tags) if node.tags else "",
            (node.summary or "")[:60],
            file_str,
        )

    console.print(table)
    console.print(f"\n[dim]{len(results)} result(s)[/dim]")


def _resolve_node_type(raw: str) -> "NodeType | None":
    """Resolve a user-friendly type string to a NodeType enum."""
    from ..models import NodeType

    aliases = {
        "rule": NodeType.RULE,
        "role": NodeType.ROLE,
        "skill": NodeType.SKILL,
        "tool": NodeType.TOOL,
        "document": NodeType.DOCUMENT,
        "doc": NodeType.DOCUMENT,
        "section": NodeType.SECTION,
        "project": NodeType.PROJECT,
        "category": NodeType.CATEGORY,
    }
    return aliases.get(raw.strip().lower())


def _flatten(node) -> list:
    """Flatten a knowledge tree into a list of all nodes (excluding root/category containers)."""
    from ..models import NodeType

    results = []
    if node.node_type not in (NodeType.ROOT, NodeType.CATEGORY):
        results.append(node)
    for child in node.children:
        results.extend(_flatten(child))
    return results
