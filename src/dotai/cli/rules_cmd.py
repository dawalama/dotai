"""CLI commands for rules."""

from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich.table import Table

from . import app, console


@app.command()
def rules(
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Show rules resolved for a project"),
    all: bool = typer.Option(False, "--all", "-a", help="Show all rules including disabled"),
):
    """List rules. Shows resolved active rules by default."""
    from ..store import load_config
    from ..rules import load_all_rules, resolve_rules_for_project

    config = load_config()

    if all:
        rule_list = load_all_rules(config)
    elif project:
        rule_list = resolve_rules_for_project(config, project)
    else:
        rule_list = load_all_rules(config)

    if not rule_list:
        console.print("[dim]No rules found. Use `dotai learn` to add rules.[/dim]")
        return

    # Check project disabled list for display
    disabled_ids: set[str] = set()
    if project:
        proj = config.get_project(project)
        if proj:
            disabled_ids = set(proj.disabled_rules)

    title = f"Rules (project: {project})" if project else "Rules"
    table = Table(title=title)
    table.add_column("Name", style="bold")
    table.add_column("Status", style="green")
    table.add_column("Scope", style="dim")
    table.add_column("Globs", style="cyan")
    table.add_column("Tags", style="dim")
    table.add_column("Description")

    for rule in rule_list:
        if rule.id in disabled_ids:
            status = "[red]disabled (project)[/red]"
        elif not rule.enabled:
            status = "[red]disabled[/red]"
        else:
            status = "[green]on[/green]"
        table.add_row(
            rule.id,
            status,
            rule.scope,
            ", ".join(rule.globs) if rule.globs else "",
            ", ".join(rule.tags),
            rule.description[:50],
        )

    console.print(table)


@app.command()
def toggle(
    rule_id: str = typer.Argument(..., help="Rule ID to toggle (e.g. no-useeffect)"),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Toggle for a specific project only"),
    on: bool = typer.Option(False, "--on", help="Enable the rule"),
    off: bool = typer.Option(False, "--off", help="Disable the rule"),
):
    """Enable or disable a rule globally or for a specific project.

    Globally:  dotai toggle no-useeffect --off
    Per project: dotai toggle no-useeffect --off -p my-legacy-app
    """
    from ..store import load_config
    from ..rules import toggle_rule_global, toggle_rule_for_project

    if not on and not off:
        console.print("[red]Specify --on or --off[/red]")
        raise typer.Exit(1)

    config = load_config()
    enabled = on  # --on → True, --off → False

    if project:
        # Disable/enable a global rule for this project only
        ok = toggle_rule_for_project(config, project, rule_id, disabled=not enabled)
        if ok:
            state = "enabled" if enabled else "disabled"
            console.print(f"[green]Rule '{rule_id}' {state} for project '{project}'[/green]")
        else:
            console.print(f"[red]Project '{project}' not found or rule already in that state[/red]")
            raise typer.Exit(1)
    else:
        # Toggle globally in the rule's frontmatter
        rules_dir = config.global_rules_path
        ok = toggle_rule_global(rule_id, rules_dir, enabled)
        if ok:
            state = "enabled" if enabled else "disabled"
            console.print(f"[green]Rule '{rule_id}' {state} globally[/green]")
        else:
            console.print(f"[red]Rule '{rule_id}' not found in {rules_dir}[/red]")
            raise typer.Exit(1)


@app.command()
def learn(
    title: str = typer.Argument(..., help="Short title for the rule or learning"),
    from_file: Optional[str] = typer.Option(None, "--from-file", "-f", help="Import rule from a file"),
    issue: Optional[str] = typer.Option(None, "--issue", "-i", help="What went wrong (inline mode)"),
    correction: Optional[str] = typer.Option(None, "--correction", "-c", help="What to do instead (inline mode)"),
    description: Optional[str] = typer.Option(None, "--description", "-d", help="One-line description"),
    globs: Optional[str] = typer.Option(None, "--globs", "-g", help="File patterns this rule applies to (e.g. '*.tsx,*.ts')"),
    tags: Optional[str] = typer.Option(None, "--tags", "-t", help="Comma-separated tags"),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Project name (writes to project rules/)"),
):
    """Add a rule from a file or record an inline learning.

    From file (creates structured rule in ~/.ai/rules/):
      dotai learn "no-useEffect" -f react-rule.md -g "*.tsx,*.ts"

    Inline learning (appends to rules.md):
      dotai learn "title" -i "what went wrong" -c "what to do instead"
    """
    from ..store import load_config

    if not from_file and not (issue and correction):
        console.print("[red]Provide --from-file, or --issue and --correction[/red]")
        raise typer.Exit(1)

    config = load_config()

    if from_file:
        from ..rules import create_rule_from_file

        source = Path(from_file).expanduser().resolve()
        if not source.exists():
            console.print(f"[red]File not found: {source}[/red]")
            raise typer.Exit(1)

        # Determine target rules directory
        if project:
            proj = config.get_project(project)
            if not proj:
                console.print(f"[red]Project '{project}' not found[/red]")
                raise typer.Exit(1)
            rules_dir = proj.rules_path
        else:
            rules_dir = config.global_rules_path

        glob_list = [g.strip() for g in globs.split(",")] if globs else None
        tag_list = [t.strip() for t in tags.split(",")] if tags else None

        dest = create_rule_from_file(
            source_path=source,
            name=title,
            dest_dir=rules_dir,
            description=description,
            globs=glob_list,
            tags=tag_list,
        )

        console.print(f"[green]Rule created:[/green] {title}")
        console.print(f"  [dim]{dest}[/dim]")

        # Show what was detected
        from ..rules import parse_rule_file
        rule = parse_rule_file(dest)
        if rule:
            if rule.tags:
                console.print(f"  Tags: {', '.join(rule.tags)}")
            if rule.globs:
                console.print(f"  Globs: {', '.join(rule.globs)}")
            console.print(f"  Description: {rule.description}")
    else:
        # Inline learning — append to rules.md
        if project:
            proj = config.get_project(project)
            if not proj:
                console.print(f"[red]Project '{project}' not found[/red]")
                raise typer.Exit(1)
            rules_path = proj.full_ai_path / "rules.md"
        else:
            rules_path = config.global_ai_dir / "rules.md"

        rules_path.parent.mkdir(parents=True, exist_ok=True)

        entry = f"\n### {datetime.now().strftime('%Y-%m-%d')}: {title}\n"
        entry += f"**Issue:** {issue}\n"
        entry += f"**Correction:** {correction}\n"

        with open(rules_path, "a") as f:
            f.write(entry)

        console.print(f"[green]Recorded learning:[/green] {title}")
