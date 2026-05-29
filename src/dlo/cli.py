from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from sqlalchemy import select

from dlo.config import data_dir, database_url
from dlo.crawl import crawl_directory
from dlo.db import get_engine, session_scope
from dlo.models import Base, FileRecord

console = Console()


@click.group()
def main() -> None:
    """Digital Life Organizer: crawl, metadata, duplicates."""


@main.command()
def init_db() -> None:
    """Create database tables."""
    engine = get_engine()
    Base.metadata.create_all(engine)
    console.print(f"[green]Database ready[/green] at {database_url()}")


@main.command()
@click.argument("directory", type=click.Path(exists=True, file_okay=False, dir_okay=True))
@click.option(
    "--dry-run/--execute",
    default=True,
    help="Read-only pass (default). --execute will apply renames when supported.",
)
@click.option("--no-report", is_flag=True, help="Skip writing the JSON audit report.")
def crawl(directory: str, dry_run: bool, no_report: bool) -> None:
    """Scan a directory tree and index file metadata (no renames in dry-run mode)."""
    root = Path(directory)
    try:
        result = crawl_directory(root, dry_run=dry_run, write_report=not no_report)
    except RuntimeError as exc:
        raise click.ClickException(str(exc)) from exc

    resolved = root.resolve()
    console.print(
        f"[green]Crawled[/green] {result.files_scanned} files under [cyan]{resolved}[/cyan]",
    )
    if result.report_path is not None:
        console.print(f"Audit report: [cyan]{result.report_path}[/cyan]")


@main.command()
@click.option("--limit", default=20, help="Max rows to show.")
def status(limit: int) -> None:
    """Show data directory and recent indexed files."""
    console.print(f"Data dir: [cyan]{data_dir()}[/cyan]")
    console.print(f"Database: [cyan]{database_url()}[/cyan]")

    with session_scope() as session:
        rows = session.scalars(select(FileRecord).order_by(FileRecord.scanned_at.desc()).limit(limit)).all()

    if not rows:
        console.print("[dim]No files indexed yet. Run crawl scripts to populate.[/dim]")
        return

    table = Table(title=f"Recent files (up to {limit})")
    table.add_column("Path")
    table.add_column("Size", justify="right")
    table.add_column("Hash")
    for row in rows:
        table.add_row(row.path, str(row.size_bytes or ""), row.content_hash or "")
    console.print(table)


if __name__ == "__main__":
    main()
