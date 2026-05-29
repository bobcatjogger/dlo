# dlo — Digital Life Organizer

Tools to crawl your filesystem, store metadata, and surface duplicates for archive or deletion.

Part of the [codez](../) workspace.

## Stack

| Layer | Choice |
|-------|--------|
| Python | 3.11+, CLI via Click, SQLAlchemy models |
| Shell | zsh scripts in `scripts/zsh/` |
| Database | **SQLite** by default (`data/dlo.db`) — no server, portable, ideal for local indexing. Set `DLO_DATABASE_URL` to Postgres when you need multi-machine sync. |
| Migrations | Alembic |

## Quick start

```bash
cd ~/codez/dlo
python3.13 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env
./scripts/zsh/init-db.zsh

dlo status
dlo init-db
dlo crawl /path/to/staging --dry-run
```

Or: `make install` then `make db-init`.

## Layout

```
src/dlo/            Python package (models, db, CLI)
scripts/zsh/        zsh entrypoints and shared helpers
alembic/            schema migrations
tests/              pytest
data/               local DB and artifacts (gitignored)
```

## Environment

| Variable | Default |
|----------|---------|
| `DLO_DATA_DIR` | `./data` |
| `DLO_DATABASE_URL` | `sqlite:///<data>/dlo.db` |

## Development

```bash
make test
make lint
make format
```
