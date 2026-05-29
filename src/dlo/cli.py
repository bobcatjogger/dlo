from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from sqlalchemy import select

from dlo.config import data_dir, database_url
from dlo.crawl import crawl_directory
from dlo.db import get_engine, session_scope
from dlo.dedupe import run_dedupe
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
@click.option("--limit", default=20, help="Max duplicate groups to show per match type.")
@click.option("--min-size", default=0, show_default=True, help="Ignore files smaller than N bytes.")
@click.option("--path-prefix", default=None, help="Only consider files under this path prefix.")
@click.option("--no-report", is_flag=True, help="Skip writing the JSON dedupe report.")
def dedupe(limit: int, min_size: int, path_prefix: str | None, no_report: bool) -> None:
    """Find likely duplicate files from indexed metadata in the database."""
    with session_scope() as session:
        result = run_dedupe(
            session,
            path_prefix=path_prefix,
            min_size_bytes=min_size,
            write_report=not no_report,
        )
        groups_by_type = result.groups_by_type

    total_groups = sum(len(groups) for groups in groups_by_type.values())
    total_paths = sum(group.count for groups in groups_by_type.values() for group in groups)
    console.print(
        f"Found [green]{total_groups}[/green] duplicate groups "
        f"covering [green]{total_paths}[/green] file paths",
    )
    console.print(
        f"Persisted [green]{result.persisted_hash_groups}[/green] hash duplicate groups to database",
    )

    labels = {
        "same_name": "Same basename",
        "same_size_type": "Same size + MIME type, different names",
        "same_hash": "Same content hash",
    }
    for match_type, groups in groups_by_type.items():
        console.print(f"\n[bold]{labels[match_type]}[/bold] ({len(groups)} groups)")
        if not groups:
            console.print("[dim]None found.[/dim]")
            continue

        table = Table(show_header=True, header_style="bold")
        table.add_column("Key")
        table.add_column("Count", justify="right")
        table.add_column("Sample paths")
        for group in groups[:limit]:
            sample = "\n".join(group.paths[:3])
            if len(group.paths) > 3:
                sample += f"\n[dim]... +{len(group.paths) - 3} more[/dim]"
            table.add_row(group.key, str(group.count), sample)
        if len(groups) > limit:
            console.print(f"[dim]Showing {limit} of {len(groups)} groups.[/dim]")
        console.print(table)

    if result.report_path is not None:
        console.print(f"\nDedupe report: [cyan]{result.report_path}[/cyan]")


@main.command()
@click.option("--limit", default=20, help="Max rows to show.")
def status(limit: int) -> None:
    """Show data directory and recent indexed files."""
    console.print(f"Data dir: [cyan]{data_dir()}[/cyan]")
    console.print(f"Database: [cyan]{database_url()}[/cyan]")

    with session_scope() as session:
        stmt = select(FileRecord).order_by(FileRecord.scanned_at.desc()).limit(limit)
        rows = session.scalars(stmt).all()

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
