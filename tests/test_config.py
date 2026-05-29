from pathlib import Path

from dlo.config import data_dir, database_url


def test_database_url_defaults_to_sqlite(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DLO_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("DLO_DATABASE_URL", raising=False)
    assert database_url().startswith("sqlite:///")
    assert data_dir() == tmp_path.resolve()
