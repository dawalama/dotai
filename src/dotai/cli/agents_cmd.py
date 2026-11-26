"""CLI for user-level coding-agent projection and adapters."""

import sys
from pathlib import Path
from typing import Optional

import typer

from . import app, console


@app.command("agent")
def agent(
    action: str = typer.Argument(..., help="Action: setup, status, last, remove"),
    name: str = typer.Argument(..., help="Agent target: claude, codex, gemini, agents, or all"),
    apply: bool = typer.Option(False, "--apply", help="Back up and apply the displayed change"),
    mode: str = typer.Option(
        "native",
        "--mode",
        help="Delivery mode for claude: native (default, compiles to ~/.claude/rules/ & skills/) or cli-bootstrap (legacy)",
    ),
):
    """Project personal ~/.ai/ guidance into native user-level agent directories without touching repos."""
    from ..agents import (
        apply_agent_plan,
        claude_adapter_status,
        plan_claude_remove,
        plan_claude_setup,
    )
    from ..context import load_resolution_receipt
    from ..projection import (
        SUPPORTED_TARGETS,
        apply_projection_plan,
        plan_projection,
        plan_projection_remove,
        projection_status,
    )
    from ..store import get_config_dir, load_config

    action = action.lower()
    name = name.lower()
    mode = mode.lower()

    if mode not in ("native", "cli-bootstrap"):
        console.print("[red]Invalid --mode. Use: native or cli-bootstrap[/red]")
        raise typer.Exit(2)

    if action == "last":
        if name != "claude":
            console.print("[red]`agent last` is only recorded for legacy cli-bootstrap receipts (claude).[/red]")
            raise typer.Exit(2)
        receipt = load_resolution_receipt("claude", get_config_dir() / "receipts")
        if not receipt:
            console.print("[yellow]No Claude dotai resolution receipt has been recorded.[/yellow]")
            console.print(
                "  Native projection (`~/.claude/rules/`) loads directly without CLI receipts. "
                "Use `dotai agent status claude` to check projection sync."
            )
            return
        console.print("Last Claude dotai resolution")
        console.print(f"  Time: {receipt.get('resolved_at', 'unknown')}")
        console.print(f"  Project: {receipt.get('project_path', 'unknown')}")
        console.print(f"  Task: {receipt.get('task') or 'not provided'}")
        provisional = bool(receipt.get("provisional"))
        console.print(f"  Resolution: {'provisional' if provisional else 'resolved'}")
        files = receipt.get("files") or []
        console.print(f"  File scope: {'provided' if files else 'unknown'}")
        console.print(f"  Files: {', '.join(files) if files else 'not known'}")
        console.print(f"  Skill: {receipt.get('skill') or 'none'}")
        console.print(f"  Role: {receipt.get('role') or 'none'}")
        rules = receipt.get("expanded_rules") or []
        prefs = receipt.get("preferences") or []
        console.print(f"  Expanded rules: {', '.join(rules) if rules else 'none'}")
        console.print(f"  Preferences: {', '.join(prefs) if prefs else 'none'}")
        selections = receipt.get("selections") or []
        if selections:
            console.print("  Why:")
            for selection in selections:
                console.print(
                    f"    {selection.get('kind')}:{selection.get('item_id')} — "
                    f"{selection.get('reason')}"
                )
        if provisional:
            console.print(
                "\n[yellow]Warning: this workflow requires a second dotai resolution "
                "with affected files.[/yellow]"
            )
        return

    if mode == "cli-bootstrap":
        if name != "claude":
            console.print("[red]Legacy cli-bootstrap mode is only available for claude.[/red]")
            raise typer.Exit(2)
        if action == "status":
            status, detail = claude_adapter_status()
            color = "green" if status == "configured" else "yellow"
            console.print(f"Claude cli-bootstrap adapter: [{color}]{status}[/{color}]")
            console.print(f"  {detail}")
            return
        try:
            if action == "setup":
                plan = plan_claude_setup(command=str(Path(sys.argv[0]).resolve()))
            elif action == "remove":
                plan = plan_claude_remove()
            else:
                console.print("[red]Unknown action. Use: setup, status, last, remove[/red]")
                raise typer.Exit(2)
        except ValueError as error:
            console.print(f"[red]{error}[/red]")
            raise typer.Exit(2) from error

        console.print(f"Claude cli-bootstrap plan · {plan.action}")
        console.print(f"  Path: {plan.path}")
        console.print(f"  Change: {plan.detail}")
        if plan.action == "none":
            return
        if not apply:
            console.print(
                f"\n[dim]Preview only. Run `dotai agent {action} claude --mode cli-bootstrap --apply` to apply.[/dim]"
            )
            return
        backup = apply_agent_plan(plan, get_config_dir() / "backups" / "agents" / "claude")
        console.print(f"[green]Claude cli-bootstrap {action} complete.[/green]")
        if backup:
            console.print(f"Backup: {backup}")
        return

    # Native projection mode (default)
    if name == "all":
        targets = list(SUPPORTED_TARGETS)
    elif name in SUPPORTED_TARGETS:
        targets = [name]
    else:
        supported = ", ".join((*SUPPORTED_TARGETS, "all"))
        console.print(f"[red]Unsupported agent: {name}. Supported: {supported}[/red]")
        raise typer.Exit(2)

    config = load_config()

    if action == "status":
        for target in targets:
            status, detail = projection_status(target, config)
            color = {"configured": "green", "out-of-sync": "yellow", "not-configured": "dim"}.get(status, "red")
            console.print(f"{target} (native): [{color}]{status}[/{color}]")
            console.print(f"  {detail}")
            if target == "claude":
                legacy_status, _ = claude_adapter_status()
                if legacy_status == "configured":
                    console.print(
                        "  [yellow]Note: legacy cli-bootstrap block is still in ~/.claude/CLAUDE.md; "
                        "run `dotai agent remove claude --mode cli-bootstrap --apply` to clean it up.[/yellow]"
                    )
        return

    if action not in ("setup", "remove"):
        console.print("[red]Unknown action. Use: setup, status, last, remove[/red]")
        raise typer.Exit(2)

    any_changes = False
    for target in targets:
        try:
            if action == "setup":
                plan = plan_projection(target, config)
            else:
                keep_shared = (
                    name == "all" and target in ("codex", "gemini")
                ) if name == "all" else None
                plan = plan_projection_remove(
                    target, config, keep_shared_skills=keep_shared
                )
        except ValueError as error:
            console.print(f"[red]{target}: {error}[/red]")
            raise typer.Exit(2) from error

        console.print(f"[bold]{target}[/bold] native {action} plan · {len(plan.operations)} operation(s)")
        for op in plan.operations:
            console.print(f"  [{op.action}] {op.path} — {op.detail}")
        for warning in plan.warnings:
            console.print(f"  [yellow]Warning: {warning}[/yellow]")

        if not plan.has_changes:
            console.print("  [dim]Already up to date.[/dim]")
            continue

        any_changes = True
        if apply:
            backup = apply_projection_plan(plan, get_config_dir() / "backups" / "agents")
            console.print(f"  [green]Applied {len(plan.operations)} operation(s) for {target}.[/green]")
            if backup:
                console.print(f"  Backup: {backup}")

    if any_changes and not apply:
        console.print(
            f"\n[dim]Preview only. Run `dotai agent {action} {name} --apply` to apply.[/dim]"
        )
