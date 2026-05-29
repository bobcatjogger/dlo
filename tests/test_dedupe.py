from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select

from dlo.db import get_engine, session_scope
from dlo.dedupe import find_duplicates, run_dedupe
from dlo.models import Base, DuplicateGroup, FileRecord


def _seed(session, records: list[FileRecord]) -> None:
    session.add_all(records)
    session.commit()


def _make_record(
    path: str,
    *,
    size_bytes: int | None = None,
    mime_type: str | None = None,
    content_hash: str | None = None,
) -> FileRecord:
    return FileRecord(
        path=path,
        size_bytes=size_bytes,
        mime_type=mime_type,
        content_hash=content_hash,
    )


def test_find_same_name_duplicates(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DLO_DATA_DIR", str(tmp_path))
    import dlo.db as db_module

    db_module._engine = None
    db_module._SessionLocal = None
    Base.metadata.create_all(get_engine())

    with session_scope() as session:
        _seed(
            session,
            [
                _make_record("/staging/a/photo.jpg", size_bytes=100, mime_type="image/jpeg"),
                _make_record("/staging/b/photo.jpg", size_bytes=200, mime_type="image/jpeg"),
                _make_record("/staging/c/other.txt", size_bytes=50, mime_type="text/plain"),
            ],
        )

    with session_scope() as session:
        groups = find_duplicates(session)

    same_name = groups["same_name"]
    assert len(same_name) == 1
    assert same_name[0].key == "photo.jpg"
    assert same_name[0].count == 2


def test_find_same_size_type_with_different_names(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DLO_DATA_DIR", str(tmp_path))
    import dlo.db as db_module

    db_module._engine = None
    db_module._SessionLocal = None
    Base.metadata.create_all(get_engine())

    with session_scope() as session:
        _seed(
            session,
            [
                _make_record("/staging/a/copy.pdf", size_bytes=4096, mime_type="application/pdf"),
                _make_record("/staging/b/scan.pdf", size_bytes=4096, mime_type="application/pdf"),
                _make_record("/staging/c/tiny.pdf", size_bytes=100, mime_type="application/pdf"),
            ],
        )

    with session_scope() as session:
        groups = find_duplicates(session)

    same_size_type = groups["same_size_type"]
    assert len(same_size_type) == 1
    assert same_size_type[0].count == 2
    assert "application/pdf" in same_size_type[0].key
    assert "<1MB" in same_size_type[0].key


def test_find_same_hash_duplicates(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DLO_DATA_DIR", str(tmp_path))
    import dlo.db as db_module

    db_module._engine = None
    db_module._SessionLocal = None
    Base.metadata.create_all(get_engine())

    with session_scope() as session:
        _seed(
            session,
            [
                _make_record(
                    "/staging/a/file.bin",
                    size_bytes=10,
                    mime_type="application/octet-stream",
                    content_hash="abc123",
                ),
                _make_record(
                    "/staging/b/duplicate.bin",
                    size_bytes=10,
                    mime_type="application/octet-stream",
                    content_hash="abc123",
                ),
            ],
        )

    with session_scope() as session:
        groups = find_duplicates(session)

    same_hash = groups["same_hash"]
    assert len(same_hash) == 1
    assert same_hash[0].key == "abc123"
    assert same_hash[0].count == 2


def test_path_prefix_filters_records(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DLO_DATA_DIR", str(tmp_path))
    import dlo.db as db_module

    db_module._engine = None
    db_module._SessionLocal = None
    Base.metadata.create_all(get_engine())

    with session_scope() as session:
        _seed(
            session,
            [
                _make_record(
                    "/Volumes/staged_ext/a/readme.txt",
                    size_bytes=10,
                    mime_type="text/plain",
                ),
                _make_record(
                    "/Volumes/staged_ext/b/readme.txt",
                    size_bytes=10,
                    mime_type="text/plain",
                ),
                _make_record(
                    "/Volumes/other/readme.txt",
                    size_bytes=10,
                    mime_type="text/plain",
                ),
            ],
        )

    with session_scope() as session:
        groups = find_duplicates(session, path_prefix="/Volumes/staged_ext")

    assert len(groups["same_name"]) == 1
    assert groups["same_name"][0].count == 2


def test_run_dedupe_persists_hash_groups_and_writes_report(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DLO_DATA_DIR", str(tmp_path / "data"))
    import dlo.db as db_module

    db_module._engine = None
    db_module._SessionLocal = None
    Base.metadata.create_all(get_engine())

    with session_scope() as session:
        _seed(
            session,
            [
                _make_record(
                    "/staging/a/file.bin",
                    size_bytes=10,
                    mime_type="application/octet-stream",
                    content_hash="abc123",
                ),
                _make_record(
                    "/staging/b/duplicate.bin",
                    size_bytes=10,
                    mime_type="application/octet-stream",
                    content_hash="abc123",
                ),
            ],
        )

    with session_scope() as session:
        result = run_dedupe(session, path_prefix="/staging", write_report=True)

    assert result.persisted_hash_groups == 1
    assert result.report_path is not None
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert report["summary"]["same_hash"] == 1
    assert report["duplicate_groups"][0]["duplicate_group_id"] is not None
    assert report["duplicate_groups"][0]["files"][0]["file_size"] == "<1MB"

    with session_scope() as session:
        db_groups = list(session.scalars(select(DuplicateGroup)).all())
        assert len(db_groups) == 1
        assert db_groups[0].content_hash == "abc123"
