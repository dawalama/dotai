"""CLI commands for sync, primer, index, tree, and search."""

from pathlib import Path
from typing import Optional

import typer
from rich.table import Table

from . import app, console


@app.command()
def sync(
    path: str = typer.Argument(".", help="Project path to sync into"),
    agents: Optional[str] = typer.Option(None, help="Comma-separated: claude,cursor,gemini,generic"),
):
    """Sync ~/.ai/ knowledge into agent-specific config files.

    Generates CLAUDE.md, .cursorrules, GEMINI.md, and/or AGENTS.md with
    full context about available roles, skills, rules, and gotchas.
    """
    from ..store import load_config
    from ..sync import sync_project

    config = load_config()
    project_path = Path(path).expanduser().resolve()

    # Find project name
    project_config = next((p for p in config.projects if p.path == project_path), None)
    project_name = project_config.name if project_config else None

    agent_list = agents.split(",") if agents else None
    written = sync_project(project_path, config, project_name, agent_list)

    for f in written:
        console.print(f"  [green]Synced[/green] {f}")


@app.command()
def primer(
    project: Optional[str] = typer.Option(None, help="Scope to a specific project"),
):
    """Print the agent primer to stdout (for piping into other tools)."""
    from ..store import load_config
    from ..sync import generate_primer

    config = load_config()
    console.print(generate_primer(config, project))


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
