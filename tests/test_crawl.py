from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

from dlo.crawl import (
    AUDIT_ALGORITHM_VERSION,
    _root_slug,
    _rotate_audit_reports,
    build_audit_report_name,
    crawl_directory,
    format_file_size,
    get_proposed_name,
    hash_file_content,
)


def test_format_file_size() -> None:
    one_mb = 1024 * 1024
    one_gb = 1024 * 1024 * 1024
    assert format_file_size(0) == "empty"
    assert format_file_size(512_000) == "<1MB"
    assert format_file_size(one_mb) == "1.0MB"
    assert format_file_size(int(2.5 * one_mb)) == "2.5MB"
    assert format_file_size(one_gb) == "1.0GB"
    assert format_file_size(int(3.2 * one_gb)) == "3.2GB"


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
    expected_name = build_audit_report_name(
        (tmp_path / "staging").resolve(),
        datetime.fromisoformat(
            json.loads(result.report_path.read_text(encoding="utf-8"))["audit_timestamp"],
        ),
    )
    assert result.report_path == data / expected_name
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert report["total_files_scanned"] == 1
    assert report["dry_run"] is True
    assert report["algorithm_version"] == AUDIT_ALGORITHM_VERSION
    assert len(report["proposed_changes"]) == 1
    assert report["proposed_changes"][0]["file_size"] == "<1MB"
    assert report["proposed_changes"][0]["content_hash"] is not None


def test_hash_file_content(tmp_path: Path) -> None:
    file_a = tmp_path / "a.txt"
    file_b = tmp_path / "b.txt"
    file_a.write_text("same", encoding="utf-8")
    file_b.write_text("same", encoding="utf-8")

    assert hash_file_content(file_a) == hash_file_content(file_b)
    assert hash_file_content(file_a) != hash_file_content(tmp_path / "missing.txt")


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


def test_build_audit_report_name(tmp_path: Path) -> None:
    root = tmp_path / "staging"
    root.mkdir()
    scanned_at = datetime(2026, 5, 29, 20, 52, 28, tzinfo=UTC)

    name = build_audit_report_name(root, scanned_at)

    assert name.endswith(f"_v{AUDIT_ALGORITHM_VERSION}.json")
    assert "20260529T205228Z" in name
    assert _root_slug(root) in name


def test_rotate_audit_reports_keeps_last_three(tmp_path: Path) -> None:
    root = Path("/Volumes/staged_ext")
    slug = _root_slug(root)
    for index in range(5):
        report_name = f"audit_{slug}_2026052{index}T120000Z_v{AUDIT_ALGORITHM_VERSION}.json"
        (tmp_path / report_name).write_text("{}", encoding="utf-8")

    _rotate_audit_reports(tmp_path, root)

    remaining = sorted(tmp_path.glob(f"audit_{slug}_*_v{AUDIT_ALGORITHM_VERSION}.json"))
    assert len(remaining) == 3
    assert remaining[0].name == f"audit_{slug}_20260522T120000Z_v{AUDIT_ALGORITHM_VERSION}.json"
    assert remaining[-1].name == f"audit_{slug}_20260524T120000Z_v{AUDIT_ALGORITHM_VERSION}.json"
