"""CLI command for watching ~/.ai/ and auto-syncing on changes."""

from pathlib import Path
from typing import Optional

import typer

from . import app, console


@app.command()
def watch(
    path: str = typer.Argument(".", help="Project path to sync into"),
    agents: Optional[str] = typer.Option(None, help="Comma-separated: claude,cursor,gemini,generic"),
):
    """Watch ~/.ai/ for changes and auto-resync agent config files.

    Runs in the foreground. Press Ctrl+C to stop.
    """
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    import time

    from ..store import load_config
    from ..sync import sync_project

    project_path = Path(path).expanduser().resolve()

    # Determine which directories to watch
    config = load_config()
    watch_dirs = [config.global_ai_dir]

    # Also watch project-local .ai/ if it exists
    project_ai = project_path / ".ai"
    if project_ai.exists():
        watch_dirs.append(project_ai)

    agent_list = agents.split(",") if agents else None

    def do_sync():
        """Run sync and report results."""
        try:
            cfg = load_config()
            project_config = next((p for p in cfg.projects if p.path == project_path), None)
            project_name = project_config.name if project_config else None
            written = sync_project(project_path, cfg, project_name, agent_list)
            for f in written:
                console.print(f"  [green]Synced[/green] {f}")
        except Exception as e:
            console.print(f"  [red]Sync error:[/red] {e}")

    class SyncHandler(FileSystemEventHandler):
        """Debounced handler that resyncs on .md/.json file changes."""

        def __init__(self):
            self._last_sync = 0.0
            self._debounce_seconds = 1.0

        def on_modified(self, event):
            self._maybe_sync(event)

        def on_created(self, event):
            self._maybe_sync(event)

        def on_deleted(self, event):
            self._maybe_sync(event)

        def _maybe_sync(self, event):
            if event.is_directory:
                return
            # Only react to relevant file types
            src = Path(event.src_path)
            if src.suffix not in (".md", ".json", ".yaml", ".yml"):
                return

            now = time.time()
            if now - self._last_sync < self._debounce_seconds:
                return
            self._last_sync = now

            rel = src.name
            console.print(f"\n[dim]Changed:[/dim] {rel}")
            do_sync()

    # Initial sync
    console.print(f"[bold]Watching for changes...[/bold]")
    console.print(f"  Project: {project_path}")
    for d in watch_dirs:
        console.print(f"  Watching: {d}")
    console.print(f"  Press Ctrl+C to stop.\n")
    do_sync()

    # Start watching
    observer = Observer()
    handler = SyncHandler()
    for d in watch_dirs:
        observer.schedule(handler, str(d), recursive=True)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        console.print("\n[dim]Stopped watching.[/dim]")
        observer.stop()
    observer.join()
