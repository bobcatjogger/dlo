from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def data_dir() -> Path:
    raw = os.environ.get("CODEZ_DATA_DIR", str(PROJECT_ROOT / "data"))
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = (PROJECT_ROOT / path).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def database_url() -> str:
    explicit = os.environ.get("CODEZ_DATABASE_URL")
    if explicit:
        return explicit
    db_path = data_dir() / "codez.db"
    return f"sqlite:///{db_path}"
