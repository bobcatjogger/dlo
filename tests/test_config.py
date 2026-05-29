from pathlib import Path

from codez.config import data_dir, database_url


def test_database_url_defaults_to_sqlite(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CODEZ_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("CODEZ_DATABASE_URL", raising=False)
    assert database_url().startswith("sqlite:///")
    assert data_dir() == tmp_path.resolve()
