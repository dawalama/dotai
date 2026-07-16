"""CLI for user-level coding-agent adapters."""

import sys
from typing import Optional
from pathlib import Path

import typer

from . import app, console


@app.command("agent")
def agent(
    action: str = typer.Argument(..., help="Action: setup, status, last, remove"),
    name: str = typer.Argument(..., help="Agent name (currently: claude)"),
    apply: bool = typer.Option(False, "--apply", help="Back up and apply the displayed change"),
):
    """Manage user-level adapters without modifying repositories."""
    from ..agents import (
        apply_agent_plan,
        claude_adapter_status,
        plan_claude_remove,
        plan_claude_setup,
    )
    from ..context import load_resolution_receipt
    from ..store import get_config_dir

    action = action.lower()
    name = name.lower()
    if name != "claude":
        console.print(f"[red]Unsupported agent: {name}. Currently supported: claude[/red]")
        raise typer.Exit(2)

    if action == "status":
        status, detail = claude_adapter_status()
        color = "green" if status == "configured" else "yellow"
        console.print(f"Claude adapter: [{color}]{status}[/{color}]")
        console.print(f"  {detail}")
        return

    if action == "last":
        receipt = load_resolution_receipt(
            "claude", get_config_dir() / "receipts"
        )
        if not receipt:
            console.print("[yellow]No Claude dotai resolution has been recorded.[/yellow]")
            console.print(
                "  Start a new Claude session after adapter setup, then run a development task."
            )
            return
        console.print("Last Claude dotai resolution")
        console.print(f"  Time: {receipt.get('resolved_at', 'unknown')}")
        console.print(f"  Project: {receipt.get('project_path', 'unknown')}")
        console.print(f"  Task: {receipt.get('task') or 'not provided'}")
        provisional = bool(receipt.get("provisional"))
        console.print(f"  Resolution: {'provisional' if provisional else 'complete'}")
        files = receipt.get("files") or []
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

    console.print(f"Claude adapter plan · {plan.action}")
    console.print(f"  Path: {plan.path}")
    console.print(f"  Change: {plan.detail}")
    if plan.action == "none":
        return
    if not apply:
        console.print(
            f"\n[dim]Preview only. Run `dotai agent {action} claude --apply` to apply.[/dim]"
        )
        return

    backup = apply_agent_plan(
        plan, get_config_dir() / "backups" / "agents" / "claude"
    )
    console.print(f"[green]Claude adapter {action} complete.[/green]")
    if backup:
        console.print(f"Backup: {backup}")
