from __future__ import annotations

import click
from rich.console import Console
from rich.table import Table
from sqlalchemy import select

from codez.config import data_dir, database_url
from codez.db import get_engine, session_scope
from codez.models import Base, FileRecord

console = Console()


@click.group()
def main() -> None:
    """Organize your digital life: crawl, metadata, duplicates."""


@main.command()
def init_db() -> None:
    """Create database tables."""
    engine = get_engine()
    Base.metadata.create_all(engine)
    console.print(f"[green]Database ready[/green] at {database_url()}")


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
