"""CLI commands for rules."""

from pathlib import Path
from typing import Optional

import typer
from rich.table import Table

from . import app, console


@app.command()
def audit(
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Audit rules effective for a registered project"),
    all: bool = typer.Option(False, "--all", "-a", help="Include disabled rules"),
    json_output: bool = typer.Option(False, "--json", help="Emit a machine-readable report"),
    fail_on: Optional[str] = typer.Option(None, "--fail-on", help="Exit non-zero at or above: low, medium, high"),
):
    """Audit rule quality, overlap, scope, and estimated context cost.

    The audit is deterministic, local, and read-only. No rule content is sent
    to an external service.
    """
    import json

    from ..maintenance import SEVERITY_ORDER, audit_rules
    from ..store import load_config

    if fail_on and fail_on not in ("low", "medium", "high"):
        console.print("[red]--fail-on must be one of: low, medium, high[/red]")
        raise typer.Exit(2)

    config = load_config()
    if project and not config.get_project(project):
        console.print(f"[red]Project '{project}' not found[/red]")
        raise typer.Exit(1)
    report = audit_rules(config, project_name=project, include_disabled=all)

    if json_output:
        console.print_json(json.dumps(report.to_dict()))
    else:
        console.print(
            f"[bold]Rule audit[/bold] · {report.scope} · "
            f"{report.rule_count} rules · ~{report.estimated_tokens} tokens"
        )
        top_metrics = report.rule_metrics[:3]
        if len(top_metrics) >= 2 and report.estimated_tokens:
            concentrated = sum(metric.estimated_tokens for metric in top_metrics)
            percentage = concentrated / report.estimated_tokens * 100
            names = ", ".join(metric.rule_id for metric in top_metrics)
            console.print(
                f"[bold]Context concentration:[/bold] top {len(top_metrics)} rules consume "
                f"~{concentrated} tokens ({percentage:.0f}%): {names}"
            )
        recent_metrics = [metric for metric in report.rule_metrics if metric.recent_saved_tokens]
        if recent_metrics:
            console.print("[bold]Recent compression:[/bold]")
            for metric in recent_metrics:
                percentage = (
                    metric.recent_saved_tokens / metric.recent_before_tokens * 100
                    if metric.recent_before_tokens
                    else 0
                )
                console.print(
                    f"  {metric.rule_id}: ~{metric.recent_before_tokens} → "
                    f"~{metric.estimated_tokens} tokens "
                    f"([green]-{metric.recent_saved_tokens}, {percentage:.0f}%[/green])"
                )
        if not report.findings:
            console.print("[green]No deterministic rule quality issues found.[/green]")
        else:
            console.print("\n[bold]Findings[/bold]")
            for finding in report.findings:
                color = {"high": "red", "medium": "yellow", "low": "blue", "info": "dim"}[finding.severity]
                console.print(
                    f"[{color}]{finding.severity.upper()}[/{color}] "
                    f"[cyan]{finding.code}[/cyan] · {', '.join(finding.rule_ids)}"
                )
                console.print(f"  {finding.message}")
                if finding.evidence:
                    console.print(f"  [dim]{finding.evidence}[/dim]")
                console.print(f"  [bold]Next:[/bold] {finding.suggestion}\n")

    if fail_on:
        threshold = SEVERITY_ORDER[fail_on]
        if any(SEVERITY_ORDER[finding.severity] >= threshold for finding in report.findings):
            raise typer.Exit(1)


@app.command()
def compress(
    action: Optional[str] = typer.Argument(None, help="Optional action: apply"),
    proposal: Optional[Path] = typer.Argument(None, help="Versioned JSON proposal file for the apply action"),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Compress a registered project's local rules"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show candidates without applying exact duplicates"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Apply an already-approved proposal without another prompt"),
    json_output: bool = typer.Option(False, "--json", help="Emit a machine-readable compression plan"),
):
    """Plan compression or safely apply an agent-generated proposal.

    Run without an action to inspect candidates. Use `compress apply FILE` to
    validate a versioned proposal, show its diffs, back up the rules, and apply
    only approved changes.
    """
    import difflib
    import json
    import sys

    from ..maintenance import (
        apply_compression_plan,
        build_compression_plan,
        create_compression_backup,
        estimate_tokens,
        finalize_compression_backup,
        load_compression_proposal,
        write_reviewed_rule,
    )
    from ..store import load_config

    config = load_config()
    if project and not config.get_project(project):
        console.print(f"[red]Project '{project}' not found[/red]")
        raise typer.Exit(1)
    plan = build_compression_plan(config, project_name=project)

    if action:
        if action != "apply" or not proposal:
            console.print("[red]Usage: dotai compress apply <proposal.json> [--project NAME] [--yes][/red]")
            raise typer.Exit(2)
        try:
            loaded = load_compression_proposal(proposal, config, project_name=project)
        except ValueError as error:
            console.print(f"[red]Invalid compression proposal: {error}[/red]")
            raise typer.Exit(1)

        approved = []
        for change in loaded.changes:
            original = change.source_path.read_text()
            before = estimate_tokens(original)
            after = estimate_tokens(change.content)
            diff = "".join(difflib.unified_diff(
                original.splitlines(keepends=True),
                change.content.splitlines(keepends=True),
                fromfile=str(change.source_path),
                tofile=f"{change.source_path} (proposed)",
            ))
            console.print(
                f"\n[bold]{change.rule_id}[/bold] · ~{before} → ~{after} tokens "
                f"([green]-{max(0, before - after)}[/green])"
            )
            console.print(diff or "[dim]No textual change.[/dim]")
            if change.content == original:
                continue
            if yes or typer.confirm("Apply this compression?", default=False):
                approved.append(change)

        if not approved:
            console.print("\n[dim]No changes approved.[/dim]")
            return
        backup_path = create_compression_backup(config, plan, project_name=project)
        console.print(f"[bold]Backup created:[/bold] {backup_path}")
        changed = 0
        for change in approved:
            try:
                write_reviewed_rule(
                    config,
                    project_name=project,
                    rule_path=change.source_path,
                    content=change.content,
                    backup_path=backup_path,
                    expected_sha256=change.original_sha256,
                )
            except (OSError, ValueError) as error:
                console.print(f"[red]Could not apply {change.rule_id}: {error}[/red]")
                continue
            changed += 1
            console.print(f"[green]Applied:[/green] {change.rule_id}")
        manifest = finalize_compression_backup(
            config,
            backup_path,
            project_name=project,
        )
        console.print(f"\n[green]Compression complete: {changed} rule(s) changed.[/green]")
        for change in manifest["changes"]:
            console.print(
                f"  {change['rule_id']}: ~{change['before_tokens']} → "
                f"~{change['after_tokens']} tokens "
                f"([green]-{change['saved_tokens']}[/green])"
            )
        console.print(
            f"[bold]Actual context:[/bold] ~{manifest['actual_tokens_before']} → "
            f"~{manifest['actual_tokens_after']} tokens "
            f"([green]-{manifest['actual_tokens_saved']}[/green])"
        )
        console.print(f"[bold]Backup:[/bold] {backup_path}")
        return

    if json_output:
        console.print_json(json.dumps(plan.to_dict()))
    else:
        saved = plan.estimated_tokens_before - plan.estimated_tokens_after
        manual = [action for action in plan.actions if not action.automatic]
        manual_low = sum(action.estimated_tokens_saved_low for action in manual)
        manual_high = sum(action.estimated_tokens_saved_high for action in manual)
        console.print(
            f"[bold]Compression plan[/bold] · {plan.scope} · {plan.rule_count} rules"
        )
        if saved:
            console.print(
                f"Safe automatic context: ~{plan.estimated_tokens_before} → "
                f"~{plan.estimated_tokens_after} tokens ([green]-{saved}[/green])"
            )
        else:
            console.print(
                f"Estimated context: ~{plan.estimated_tokens_before} tokens · "
                "no safe automatic savings"
            )
        if manual:
            savings = (
                f" · potential manual savings ~{manual_low}-{manual_high} tokens"
                if manual_high
                else ""
            )
            console.print(f"[yellow]{len(manual)} review candidate(s)[/yellow]{savings}")
        if not plan.actions:
            console.print("[green]No safe automatic changes or review candidates found.[/green]")
        else:
            console.print("\n[bold]Actions[/bold]")
            for action in plan.actions:
                if action.estimated_tokens_saved:
                    savings = f"~{action.estimated_tokens_saved}"
                elif action.estimated_tokens_saved_high:
                    savings = (
                        f"~{action.estimated_tokens_saved_low}-"
                        f"{action.estimated_tokens_saved_high}"
                    )
                else:
                    savings = ""
                mode = "[green]APPLY[/green]" if action.automatic else "[yellow]REVIEW[/yellow]"
                savings_text = f" · potential savings {savings} tokens" if savings else ""
                console.print(
                    f"{mode} [cyan]{action.action}[/cyan] · "
                    f"{', '.join(action.rule_ids)}{savings_text}"
                )
                console.print(f"  {action.message}\n")

    if json_output or dry_run or not plan.automatic_actions:
        if plan.actions and not json_output:
            console.print("[dim]Use `/run_compress` in a synced coding agent to draft and review semantic changes.[/dim]")
        return
    if not sys.stdin.isatty():
        console.print("[dim]Exact duplicates found; run in a terminal to approve their removal.[/dim]")
        return
    if typer.confirm(
        f"Apply {len(plan.automatic_actions)} exact-duplicate action(s)?",
        default=False,
    ):
        try:
            result = apply_compression_plan(config, plan, project_name=project)
        except (OSError, ValueError) as error:
            console.print(f"[red]Compression aborted: {error}[/red]")
            raise typer.Exit(1)
        console.print(f"[green]Removed {len(result.removed_paths)} exact duplicate rule(s).[/green]")
        console.print(f"[bold]Backup:[/bold] {result.backup_path}")


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
    title: str = typer.Argument(..., help="Short title for the rule"),
    from_file: Optional[str] = typer.Option(None, "--from-file", "-f", help="Import rule from a file"),
    directive: Optional[str] = typer.Option(
        None,
        "--directive",
        help="Engineering standard, preference, or guardrail to follow",
    ),
    issue: Optional[str] = typer.Option(None, "--issue", "-i", help="What went wrong (inline mode)"),
    correction: Optional[str] = typer.Option(None, "--correction", "-c", help="What to do instead (inline mode)"),
    description: Optional[str] = typer.Option(None, "--description", "-d", help="One-line description"),
    globs: Optional[str] = typer.Option(None, "--globs", "-g", help="File patterns this rule applies to (e.g. '*.tsx,*.ts')"),
    tags: Optional[str] = typer.Option(None, "--tags", "-t", help="Comma-separated tags"),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Project name (writes to project rules/)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print the rule that would be written without saving"),
    force: bool = typer.Option(False, "--force", help="Overwrite if a similar rule already exists"),
    do_sync: bool = typer.Option(False, "--sync", help="Run `dotai sync` in the current directory after saving"),
):
    """Teach agents engineering judgment as a structured rule.

    Structured rule (default — preferred):
      dotai learn "no-useEffect" --directive "Never call useEffect directly" -g "*.tsx,*.ts"
      dotai learn "auth-header" -i "Forgot Bearer prefix" -c "Always prepend Bearer to tokens"
      dotai learn "no-useEffect" -f react-rule.md -g "*.tsx,*.ts"

    Preview without writing:
      dotai learn "auth-header" -i "..." -c "..." --dry-run
    """
    from ..store import load_config
    from ..rules import (
        build_rule_from_directive,
        build_rule_from_file,
        build_rule_from_learning,
        create_rule_from_directive,
        create_rule_from_file,
        create_rule_from_learning,
        find_duplicate_rules,
        parse_rule_file,
    )

    capture_modes = int(bool(from_file)) + int(bool(directive)) + int(bool(issue or correction))
    if capture_modes != 1 or bool(issue) != bool(correction):
        console.print(
            "[red]Provide exactly one of --from-file, --directive, "
            "or both --issue and --correction[/red]"
        )
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
        scope_label = project
    else:
        rules_dir = config.global_rules_path
        scope_label = "global"

    # --- Structured rule path (default) ---
    desc_for_dedup = description or directive or correction or ""
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
    elif directive:
        dest, content = build_rule_from_directive(
            name=title,
            dest_dir=rules_dir,
            directive=directive,
            description=description,
            globs=glob_list,
            tags=tag_list,
        )
        if dry_run:
            console.print(f"[dim]Would write {dest} ({scope_label}):[/dim]\n")
            console.print(content)
            return
        dest = create_rule_from_directive(
            name=title,
            dest_dir=rules_dir,
            directive=directive,
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
    """Refresh repository-safe local context for the current directory."""
    from ..store import get_config_dir, load_config
    from ..sync import plan_sync, sync_local_context

    config = load_config()
    project_path = Path.cwd()
    project_config = next((p for p in config.projects if p.path == project_path), None)
    project_name = project_config.name if project_config else None
    written = sync_local_context(
        plan_sync(project_path, get_config_dir()), config, project_name
    )
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
