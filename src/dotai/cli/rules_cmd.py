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
    check: bool = typer.Option(False, "--check", help="Scan for duplicates, empty bodies, weak descriptions"),
):
    """List rules. Shows resolved active rules by default.

    Use --check to audit rule quality (duplicates, empty bodies).
    """
    from ..store import load_config
    from ..rules import load_all_rules, resolve_rules_for_project, check_rule_quality

    config = load_config()

    if check:
        findings = check_rule_quality(config)
        if not findings:
            console.print("[green]No rule quality issues found.[/green]")
            return
        table = Table(title="Rule quality check")
        table.add_column("Severity", style="bold")
        table.add_column("Rule")
        table.add_column("Message")
        for f in findings:
            sev = f["severity"]
            style = "red" if sev == "error" else "yellow"
            table.add_row(f"[{style}]{sev}[/{style}]", f["rule_id"], f["message"])
        console.print(table)
        console.print(f"\n[dim]{len(findings)} finding(s)[/dim]")
        if any(f["severity"] == "error" for f in findings):
            raise typer.Exit(1)
        return

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
    append_md: bool = typer.Option(
        False,
        "--append-md",
        help="Append a freeform journal entry to rules.md instead of creating a structured rule file",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print the rule that would be written without saving"),
    force: bool = typer.Option(False, "--force", help="Overwrite if a similar rule already exists"),
    do_sync: bool = typer.Option(False, "--sync", help="Run `dotai sync` in the current directory after saving"),
):
    """Capture a convention as a structured rule (default) or freeform journal entry.

    Structured rule (default — preferred):
      dotai learn "auth-header" -i "Forgot Bearer prefix" -c "Always prepend Bearer to tokens"
      dotai learn "no-useEffect" -f react-rule.md -g "*.tsx,*.ts"

    Freeform journal (legacy):
      dotai learn "title" -i "..." -c "..." --append-md

    Preview without writing:
      dotai learn "auth-header" -i "..." -c "..." --dry-run
    """
    from ..store import load_config
    from ..rules import (
        build_rule_from_file,
        build_rule_from_learning,
        create_rule_from_file,
        create_rule_from_learning,
        find_duplicate_rules,
        parse_rule_file,
    )

    if not from_file and not (issue and correction):
        console.print("[red]Provide --from-file, or --issue and --correction[/red]")
        raise typer.Exit(1)

    config = load_config()
    glob_list = [g.strip() for g in globs.split(",")] if globs else None
    tag_list = [t.strip() for t in tags.split(",")] if tags else None

    # Resolve target directories
    if project:
        proj = config.get_project(project)
        if not proj:
            console.print(f"[red]Project '{project}' not found[/red]")
            raise typer.Exit(1)
        rules_dir = proj.rules_path
        rules_md_path = proj.full_ai_path / "rules.md"
        scope_label = project
    else:
        rules_dir = config.global_rules_path
        rules_md_path = config.global_ai_dir / "rules.md"
        scope_label = "global"

    # --- Freeform journal path (opt-in) ---
    if append_md:
        if from_file:
            console.print("[red]--append-md cannot be combined with --from-file[/red]")
            raise typer.Exit(1)
        entry = f"\n### {datetime.now().strftime('%Y-%m-%d')}: {title}\n"
        entry += f"**Issue:** {issue}\n"
        entry += f"**Correction:** {correction}\n"
        if dry_run:
            console.print(f"[dim]Would append to {rules_md_path}:[/dim]\n")
            console.print(entry)
            return
        rules_md_path.parent.mkdir(parents=True, exist_ok=True)
        with open(rules_md_path, "a") as f:
            f.write(entry)
        console.print(f"[green]Recorded freeform learning:[/green] {title}")
        console.print(f"  [dim]{rules_md_path}[/dim]")
        console.print("[dim]Tip: omit --append-md to create a structured rule agents enforce better.[/dim]")
        if do_sync:
            _run_sync_here()
        return

    # --- Structured rule path (default) ---
    desc_for_dedup = description or (correction or "")
    duplicates = find_duplicate_rules(config, title, desc_for_dedup, project_name=project)
    if duplicates and not force:
        console.print("[yellow]Similar rule(s) already exist:[/yellow]")
        for d in duplicates:
            path = d.file_path or d.id
            console.print(f"  • {d.id} [{d.scope}]: {d.description[:60]}  [dim]{path}[/dim]")
        console.print("\n[dim]Use --force to overwrite, or pick a more specific title.[/dim]")
        raise typer.Exit(1)

    if from_file:
        source = Path(from_file).expanduser().resolve()
        if not source.exists():
            console.print(f"[red]File not found: {source}[/red]")
            raise typer.Exit(1)

        dest, content = build_rule_from_file(
            source_path=source,
            name=title,
            dest_dir=rules_dir,
            description=description,
            globs=glob_list,
            tags=tag_list,
        )
        if dry_run:
            console.print(f"[dim]Would write {dest} ({scope_label}):[/dim]\n")
            console.print(content)
            return
        dest = create_rule_from_file(
            source_path=source,
            name=title,
            dest_dir=rules_dir,
            description=description,
            globs=glob_list,
            tags=tag_list,
        )
    else:
        dest, content = build_rule_from_learning(
            name=title,
            dest_dir=rules_dir,
            issue=issue or "",
            correction=correction or "",
            description=description,
            globs=glob_list,
            tags=tag_list,
        )
        if dry_run:
            console.print(f"[dim]Would write {dest} ({scope_label}):[/dim]\n")
            console.print(content)
            return
        dest = create_rule_from_learning(
            name=title,
            dest_dir=rules_dir,
            issue=issue or "",
            correction=correction or "",
            description=description,
            globs=glob_list,
            tags=tag_list,
        )

    console.print(f"[green]Rule created:[/green] {title}")
    console.print(f"  [dim]{dest}[/dim]")

    rule = parse_rule_file(dest, scope=scope_label)
    if rule:
        if rule.tags:
            console.print(f"  Tags: {', '.join(rule.tags)}")
        if rule.globs:
            console.print(f"  Globs: {', '.join(rule.globs)}")
        console.print(f"  Description: {rule.description}")

    console.print("\n[dim]Run `dotai sync` (or re-run with --sync) so agents pick this up.[/dim]")

    if do_sync:
        _run_sync_here()


def _run_sync_here() -> None:
    """Sync agent files into the current working directory."""
    from ..store import load_config
    from ..sync import sync_project

    config = load_config()
    project_path = Path.cwd()
    project_config = next((p for p in config.projects if p.path == project_path), None)
    project_name = project_config.name if project_config else None
    written = sync_project(project_path, config, project_name)
    for f in written:
        console.print(f"  [green]Synced[/green] {f}")


@app.command("import-agent")
def import_agent(
    source: str = typer.Argument(
        ...,
        help="Path to CLAUDE.md, AGENTS.md, GEMINI.md, .cursorrules, or a project directory",
    ),
    mode: str = typer.Option(
        "rules_md",
        "--mode",
        "-m",
        help="Import mode: rules_md (append to rules.md), rule (one structured rule), sections (one rule per ## heading)",
    ),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Rule name when --mode=rule"),
    project: Optional[str] = typer.Option(
        None,
        "--project",
        "-p",
        help="Registered project name (writes to that project's .ai/). Default: project-local .ai/ if cwd has one, else global",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be written without saving"),
    do_sync: bool = typer.Option(False, "--sync", help="Run `dotai sync` after import"),
):
    """Migrate existing agent context files into ~/.ai/ knowledge.

    Strips dotai-managed marker sections and imports only user-authored content.

    Examples:
      dotai import-agent CLAUDE.md
      dotai import-agent .cursorrules --mode rule --name project-conventions
      dotai import-agent AGENTS.md --mode sections --dry-run
      dotai import-agent . --mode rules_md   # scan project for known agent files
    """
    from ..store import load_config
    from ..import_agent import plan_import, apply_import_plan

    config = load_config()
    source_path = Path(source).expanduser().resolve()

    valid_modes = ("rules_md", "rule", "sections")
    if mode not in valid_modes:
        console.print(f"[red]Invalid mode '{mode}'. Choose: {', '.join(valid_modes)}[/red]")
        raise typer.Exit(1)

    if mode == "rule" and not name and source_path.is_dir():
        console.print("[red]--mode rule with a directory needs --name, or use rules_md/sections[/red]")
        raise typer.Exit(1)

    # Resolve destination .ai/ directory — prefer project-local when possible
    if project:
        proj = config.get_project(project)
        if not proj:
            console.print(f"[red]Project '{project}' not found[/red]")
            raise typer.Exit(1)
        dest_ai = proj.full_ai_path
    else:
        cwd = Path.cwd()
        registered = next((p for p in config.projects if p.path == cwd), None)
        if registered:
            dest_ai = registered.full_ai_path
        elif (cwd / ".ai").is_dir():
            dest_ai = cwd / ".ai"
        elif source_path.is_file() and (source_path.parent / ".ai").is_dir():
            dest_ai = source_path.parent / ".ai"
        elif source_path.is_dir():
            dest_ai = source_path / ".ai"
            dest_ai.mkdir(parents=True, exist_ok=True)
            (dest_ai / "rules").mkdir(exist_ok=True)
        else:
            dest_ai = config.global_ai_dir
        dest_ai.mkdir(parents=True, exist_ok=True)
        (dest_ai / "rules").mkdir(exist_ok=True)

    plan = plan_import(
        source_path,
        dest_ai,
        mode=mode,
        rule_name=name,
    )

    for w in plan.warnings:
        console.print(f"[yellow]Warning:[/yellow] {w}")

    if not plan.targets:
        console.print("[dim]Nothing to import.[/dim]")
        raise typer.Exit(0 if plan.warnings else 1)

    console.print(f"[bold]Import plan[/bold] → {dest_ai}  (mode={mode})")
    for path, content in plan.targets:
        console.print(f"  • {path}  [dim]({len(content)} chars)[/dim]")
        if dry_run:
            preview = content if len(content) < 800 else content[:800] + "\n…\n"
            console.print(f"[dim]{preview}[/dim]\n")

    if dry_run:
        console.print(f"[dim]Dry run — {len(plan.targets)} file(s) not written.[/dim]")
        return

    written = apply_import_plan(plan)
    console.print(f"[green]Imported {len(written)} file(s)[/green]")
    for p in written:
        console.print(f"  [dim]{p}[/dim]")
    console.print("\n[dim]Review the imported content, then run `dotai sync`.[/dim]")

    if do_sync:
        _run_sync_here()
