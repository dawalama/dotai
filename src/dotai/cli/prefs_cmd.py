"""CLI commands for preference / taste packs."""

from pathlib import Path
from typing import Optional

import typer
from rich.table import Table

from . import app, console


@app.command("prefs")
def prefs(
    action: Optional[str] = typer.Argument(
        None,
        help="Action: list (default), show, new, pull, use, unuse, remove",
    ),
    target: Optional[str] = typer.Argument(
        None,
        help="Pack id/name or source path/URL depending on action",
    ),
    project: Optional[str] = typer.Option(
        None, "--project", "-p", help="Registered project name"
    ),
    domain: str = typer.Option(
        "general", "--domain", "-d", help="Domain tag: cli, react, api, design, general"
    ),
    description: Optional[str] = typer.Option(
        None, "--description", help="Description for new packs"
    ),
    global_scope: bool = typer.Option(
        False, "--global", "-g", help="Use global active list / global install"
    ),
    name: Optional[str] = typer.Option(
        None, "--name", "-n", help="Pack name when pulling or creating"
    ),
    do_sync: bool = typer.Option(
        False, "--sync", help="Run dotai sync after activating/pulling"
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite / skip confirmations"),
):
    """Manage preference (taste) packs — soft, borrowable style priors.

    Preference packs are NOT hard rules. Precedence:

      hard rules > freeform rules.md > active preference packs > model default

    Examples:
      dotai prefs
      dotai prefs new "CLI Conventions" --domain cli
      dotai prefs pull ./someone-cli-taste.md --name cli-awais
      dotai prefs pull https://github.com/org/taste-packs -n cli
      dotai prefs use cli
      dotai prefs use design-eng -p my-app
      dotai prefs unuse cli
      dotai prefs show cli
      dotai prefs remove old-pack --force
    """
    from ..store import load_config
    from .. import preferences as prefmod

    config = load_config()
    action = (action or "list").lower()

    # Resolve project path for cwd-based activation
    cwd = Path.cwd()
    project_path: Path | None = None
    if not global_scope and not project:
        registered = next((p for p in config.projects if p.path == cwd), None)
        if registered:
            project = registered.name
            project_path = registered.path
        elif (cwd / ".ai").is_dir():
            project_path = cwd
    elif project and not global_scope:
        registered = config.get_project(project)
        if not registered:
            console.print(f"[red]Project '{project}' not found[/red]")
            raise typer.Exit(1)
        project_path = registered.path

    if action in ("list", "ls"):
        _cmd_list(config, project=project, project_path=project_path)
        return

    if action == "show":
        if not target:
            console.print("[red]Usage: dotai prefs show <pack-id>[/red]")
            raise typer.Exit(1)
        _cmd_show(config, target)
        return

    if action == "new":
        if not target:
            console.print("[red]Usage: dotai prefs new \"Pack Name\" [--domain cli][/red]")
            raise typer.Exit(1)
        dest = _dest_prefs_dir(config, project=project, project_path=project_path, global_scope=global_scope)
        path = prefmod.create_preference_pack(
            dest,
            name=target,
            description=description or "",
            domain=domain,
            pack_id=name,
        )
        console.print(f"[green]Created preference pack:[/green] {path}")
        console.print(f"[dim]Edit the file, then: dotai prefs use {path.stem}[/dim]")
        return

    if action == "pull":
        if not target:
            console.print("[red]Usage: dotai prefs pull <path-or-git-url> [--name id][/red]")
            raise typer.Exit(1)
        dest = _dest_prefs_dir(config, project=project, project_path=project_path, global_scope=global_scope)
        try:
            installed = prefmod.pull_preference_pack(
                target, dest, pack_name=name, domain=domain
            )
        except FileNotFoundError as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(1)
        except Exception as e:
            console.print(f"[red]Pull failed: {e}[/red]")
            raise typer.Exit(1)

        console.print(f"[green]Pulled {len(installed)} pack(s)[/green] → {dest}")
        for p in installed:
            console.print(f"  [dim]{p}[/dim]")
        # Offer activation hint
        ids = []
        for p in installed:
            pack = prefmod.parse_preference_file(p)
            if pack:
                ids.append(pack.id)
        if ids:
            console.print(f"[dim]Activate with: dotai prefs use {' '.join(ids[:1])}[/dim]")
        if do_sync:
            _run_sync()
        return

    if action == "use":
        if not target:
            console.print("[red]Usage: dotai prefs use <pack-id>[/red]")
            raise typer.Exit(1)
        pack = _find_pack_or_local(config, target, project_path)
        if not pack:
            console.print(f"[red]Pack '{target}' not found. Pull or create it first.[/red]")
            console.print("[dim]dotai prefs list[/dim]")
            raise typer.Exit(1)
        try:
            active_path = prefmod.activate_pack(
                config,
                pack.id,
                project_name=project,
                project_path=project_path if not global_scope else None,
                global_scope=global_scope or (project is None and project_path is None),
            )
        except ValueError as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(1)
        scope = "global" if "preferences-active" in str(active_path) and ".ai" not in str(active_path.parent.name) else active_path.parent
        console.print(f"[green]Active:[/green] {pack.id} ({pack.name})")
        console.print(f"  [dim]{active_path}[/dim]")
        console.print(
            "[dim]Soft prefs only — hard rules still win on conflict. Run `dotai sync`.[/dim]"
        )
        if do_sync:
            _run_sync()
        return

    if action in ("unuse", "disable"):
        if not target:
            console.print("[red]Usage: dotai prefs unuse <pack-id>[/red]")
            raise typer.Exit(1)
        from ..utils import generate_id

        pid = generate_id(target)
        try:
            active_path = prefmod.deactivate_pack(
                config,
                pid,
                project_name=project,
                project_path=project_path if not global_scope else None,
                global_scope=global_scope or (project is None and project_path is None),
            )
        except ValueError as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(1)
        console.print(f"[green]Deactivated:[/green] {pid}")
        console.print(f"  [dim]{active_path}[/dim]")
        if do_sync:
            _run_sync()
        return

    if action in ("remove", "rm", "delete"):
        if not target:
            console.print("[red]Usage: dotai prefs remove <pack-id>[/red]")
            raise typer.Exit(1)
        pack = _find_pack_or_local(
            config,
            target,
            project_path,
            include_global=global_scope or project_path is None,
        )
        if not pack or not pack.file_path:
            console.print(f"[red]Pack '{target}' not found[/red]")
            if project_path and not global_scope:
                console.print("[dim]Use --global to remove a global pack.[/dim]")
            raise typer.Exit(1)
        if not force and not typer.confirm(f"Remove preference pack '{pack.id}'?"):
            raise typer.Exit(0)
        path = pack.file_path
        if path.name == "main.md":
            # Remove folder pack
            import shutil

            shutil.rmtree(path.parent)
        else:
            path.unlink(missing_ok=True)
        owning_ai = (
            config.global_ai_dir
            if pack.scope == "global"
            else pack.file_path.parent.parent
            if pack.file_path.name != "main.md"
            else pack.file_path.parent.parent.parent
        )
        ids = prefmod.load_active_pack_ids(owning_ai)
        if pack.id in ids:
            prefmod.save_active_pack_ids(
                owning_ai, [i for i in ids if i != pack.id]
            )
        console.print(f"[green]Removed:[/green] {pack.id}")
        return

    console.print(f"[red]Unknown action '{action}'[/red]")
    console.print(
        "[dim]Actions: list, show, new, pull, use, unuse, remove[/dim]"
    )
    raise typer.Exit(1)


def _dest_prefs_dir(config, *, project, project_path, global_scope) -> Path:
    if global_scope or (not project and not project_path):
        d = config.global_preferences_path
    elif project_path:
        d = project_path / ".ai" / "preferences"
    else:
        proj = config.get_project(project)
        if not proj:
            console.print(f"[red]Project '{project}' not found[/red]")
            raise typer.Exit(1)
        d = proj.preferences_path
    d.mkdir(parents=True, exist_ok=True)
    return d


def _find_pack_or_local(
    config,
    target: str,
    project_path: Path | None,
    *,
    include_global: bool = True,
):
    from .. import preferences as prefmod
    from ..utils import generate_id

    pid = generate_id(target)
    # Project-local first
    if project_path:
        for pack in prefmod.load_preferences_from_dir(
            project_path / ".ai" / "preferences", "local"
        ):
            if pack.id == pid:
                return pack
    if include_global:
        for pack in prefmod.load_preferences_from_dir(
            config.global_preferences_path, "global"
        ):
            if pack.id == pid:
                return pack
    return None


def _cmd_list(config, *, project, project_path) -> None:
    from .. import preferences as prefmod

    packs = []
    # Merge for display: global + project local
    by_id = {}
    for p in prefmod.load_preferences_from_dir(config.global_preferences_path, "global"):
        by_id[p.id] = p
    if project_path:
        for p in prefmod.load_preferences_from_dir(
            project_path / ".ai" / "preferences", project or "local"
        ):
            by_id[p.id] = p
    elif project:
        proj = config.get_project(project)
        if proj:
            for p in prefmod.load_preferences_from_dir(proj.preferences_path, project):
                by_id[p.id] = p
    packs = list(by_id.values())

    active = set(
        prefmod.resolve_active_pack_ids(
            config, project_name=project, project_path=project_path
        )
    )

    if not packs:
        console.print("[dim]No preference packs. Create one:[/dim]")
        console.print('  [dim]dotai prefs new "CLI Conventions" --domain cli[/dim]')
        console.print("  [dim]dotai prefs pull ./taste.md --name cli[/dim]")
        return

    table = Table(title="Preference packs (soft taste)")
    table.add_column("Active")
    table.add_column("ID", style="bold")
    table.add_column("Domain", style="cyan")
    table.add_column("Scope", style="dim")
    table.add_column("Name")
    table.add_column("Description")

    for p in sorted(packs, key=lambda x: x.id):
        table.add_row(
            "[green]●[/green]" if p.id in active else "[dim]○[/dim]",
            p.id,
            p.domain,
            p.scope,
            p.name,
            (p.description or "")[:50],
        )
    console.print(table)
    console.print(
        "\n[dim]Hard rules always win over preference packs. "
        "Activate: `dotai prefs use <id>` then `dotai sync`.[/dim]"
    )


def _cmd_show(config, pack_id: str) -> None:
    pack = _find_pack_or_local(
        config,
        pack_id,
        Path.cwd() if (Path.cwd() / ".ai").is_dir() else None,
    )
    if not pack:
        console.print(f"[red]Pack '{pack_id}' not found[/red]")
        raise typer.Exit(1)

    console.print(pack.to_prompt())
    if pack.file_path:
        console.print(f"\n[dim]{pack.file_path}[/dim]")


def _run_sync() -> None:
    from ..store import load_config
    from ..sync import sync_project

    config = load_config()
    project_path = Path.cwd()
    project_config = next((p for p in config.projects if p.path == project_path), None)
    project_name = project_config.name if project_config else None
    written = sync_project(project_path, config, project_name)
    for f in written:
        console.print(f"  [green]Synced[/green] {f}")
