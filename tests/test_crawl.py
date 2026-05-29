from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

from dlo.crawl import AUDIT_REPORT_NAME, crawl_directory, get_proposed_name


def test_get_proposed_name_note(tmp_path: Path) -> None:
    doc = tmp_path / "notes.txt"
    doc.write_text("hello", encoding="utf-8")
    ts = datetime(2024, 3, 15, 12, 0, 0, tzinfo=UTC).timestamp()
    os.utime(doc, (ts, ts))

    assert get_proposed_name(doc) == "2024-03-15_note_notes.txt"


def test_get_proposed_name_media(tmp_path: Path) -> None:
    photo = tmp_path / "vacation.jpg"
    photo.write_bytes(b"\xff\xd8\xff")
    ts = datetime(2024, 3, 15, 14, 30, 45, tzinfo=UTC).timestamp()
    os.utime(photo, (ts, ts))

    assert get_proposed_name(photo) == "2024-03-15_media_vacation.jpg"


def test_crawl_directory_indexes_and_writes_report(tmp_path: Path, monkeypatch) -> None:
    import dlo.db as db_module

    data = tmp_path / "data"
    monkeypatch.setenv("DLO_DATA_DIR", str(data))
    db_module._engine = None
    db_module._SessionLocal = None

    (tmp_path / "staging").mkdir()
    (tmp_path / "staging" / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "staging" / ".hidden").write_text("skip", encoding="utf-8")

    result = crawl_directory(tmp_path / "staging", dry_run=True, write_report=True)

    assert result.files_scanned == 1
    assert result.report_path == data / AUDIT_REPORT_NAME
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert report["total_files_scanned"] == 1
    assert report["dry_run"] is True
    assert len(report["proposed_changes"]) == 1


def test_crawl_skips_bundle_internals(tmp_path: Path, monkeypatch) -> None:
    import dlo.db as db_module

    data = tmp_path / "data"
    monkeypatch.setenv("DLO_DATA_DIR", str(data))
    db_module._engine = None
    db_module._SessionLocal = None

    app = tmp_path / "staging" / "MyTool.app"
    (app / "Contents" / "MacOS").mkdir(parents=True)
    (app / "Contents" / "MacOS" / "MyTool").write_text("bin", encoding="utf-8")
    (tmp_path / "staging" / "readme.txt").write_text("hi", encoding="utf-8")

    result = crawl_directory(tmp_path / "staging", dry_run=True, write_report=True)

    assert result.files_scanned == 2
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    indexed_paths = {entry["original_path"] for entry in report["proposed_changes"]}
    assert str(app) in indexed_paths
    assert str(tmp_path / "staging" / "readme.txt") in indexed_paths
    assert not any("Contents/MacOS" in path for path in indexed_paths)
