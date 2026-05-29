# codez

Tools to crawl your filesystem, store metadata, and surface duplicates for archive or deletion.

## Stack

| Layer | Choice |
|-------|--------|
| Python | 3.11+, CLI via Click, SQLAlchemy models |
| Shell | zsh scripts in `scripts/zsh/` |
| Database | **SQLite** by default (`data/codez.db`) — no server, portable, ideal for local indexing. Set `CODEZ_DATABASE_URL` to Postgres when you need multi-machine sync. |
| Migrations | Alembic |

## Quick start

```bash
# One-time setup
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env
./scripts/zsh/init-db.zsh

# CLI
codez status
codez init-db
```

## Layout

```
src/codez/          Python package (models, db, CLI)
scripts/zsh/        zsh entrypoints and shared helpers
alembic/            schema migrations
tests/              pytest
data/               local DB and artifacts (gitignored)
```

## Environment

| Variable | Default |
|----------|---------|
| `CODEZ_DATA_DIR` | `./data` |
| `CODEZ_DATABASE_URL` | `sqlite:///<data>/codez.db` |

## Development

```bash
make test      # pytest
make lint      # ruff
make format    # ruff format
```

## Next steps

- Crawl scripts that walk paths and upsert `FileRecord` rows
- Hashing pass to populate `content_hash` and `DuplicateGroup`
- Review workflow (pending → archived / deleted)
