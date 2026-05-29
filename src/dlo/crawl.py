from __future__ import annotations

import json
import mimetypes
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from dlo.config import data_dir
from dlo.db import get_engine, session_scope
from dlo.models import Base, FileRecord

MEDIA_EXTENSIONS = frozenset({
    ".jpg", ".jpeg", ".png", ".mp4", ".mov", ".avi", ".mkv", ".webm", ".gif",
    ".bmp", ".tiff", ".ico", ".webp", ".svg", ".eps", ".raw", ".heic", ".heif",
})
DOCUMENT_EXTENSIONS = frozenset({
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt",
    ".ods", ".odp", ".odg", ".odf",
})
NOTE_EXTENSIONS = frozenset({
    ".md", ".txt", ".org", ".json", ".yaml", ".yml", ".toml", ".ini", ".conf", ".cfg",
    ".properties", ".env", ".env.local", ".env.development", ".env.production",
})
ARCHIVE_EXTENSIONS = frozenset({
    ".zip", ".tar", ".gz", ".bz2", ".rar", ".7z", ".iso", ".dmg", ".pkg",
    ".deb", ".rpm", ".msi", ".exe", ".appx", ".appxbundle", ".appxupload", ".appxuploadbundle",
})
FILE_CATEGORY_SUFFIXES: tuple[tuple[frozenset[str], str], ...] = (
    (MEDIA_EXTENSIONS, "media"),
    (DOCUMENT_EXTENSIONS, "doc"),
    (NOTE_EXTENSIONS, "note"),
    (ARCHIVE_EXTENSIONS, "archive"),
)
# Directory bundles: index the container once, never rename or crawl inside.
BUNDLE_SUFFIXES = frozenset({
    ".app", ".framework", ".bundle", ".plugin", ".kext", ".xcodeproj", ".xcworkspace",
    ".xcarchive", ".playground", ".photoslibrary", ".mlpackage",
})
SKIP_DIR_NAMES = frozenset({
    ".git", ".svn", ".hg", "__pycache__", "node_modules", "venv", ".venv",
})
AUDIT_REPORT_NAME = "digital_life_audit_report.json"


def get_proposed_name(filepath: Path, *, mtime: datetime | None = None) -> str:
    """Suggest a staged filename from modification time and file type."""
    if mtime is None:
        mtime = datetime.fromtimestamp(filepath.stat().st_mtime, tz=UTC)
    datestamp = mtime.strftime("%Y-%m-%d")
    ext = filepath.suffix.lower()
    for suffixes, label in FILE_CATEGORY_SUFFIXES:
        if ext in suffixes:
            return f"{datestamp}_{label}_{filepath.name}"
    return f"{datestamp}_{filepath.name}"


def _should_skip(name: str) -> bool:
    return name.startswith(".")


def _is_bundle(name: str) -> bool:
    return Path(name).suffix.lower() in BUNDLE_SUFFIXES


def _prune_walk_dirs(dirs: list[str]) -> list[str]:
    """Drop hidden, vendor, and bundle dirs from descent; return bundles to index here."""
    bundles = [name for name in dirs if _is_bundle(name)]
    dirs[:] = [
        name
        for name in dirs
        if not _should_skip(name) and name not in SKIP_DIR_NAMES and not _is_bundle(name)
    ]
    return bundles


def _index_path(
    session: Session,
    full_path: Path,
    scanned_at: datetime,
    proposed_changes: list[dict[str, object]],
) -> None:
    try:
        stat = full_path.stat()
    except OSError:
        return

    mtime = datetime.fromtimestamp(stat.st_mtime, tz=UTC)
    proposed_name = get_proposed_name(full_path, mtime=mtime)
    mime_type, _ = mimetypes.guess_type(full_path.name)
    path_str = str(full_path)

    record = session.scalar(select(FileRecord).where(FileRecord.path == path_str))
    if record is None:
        record = FileRecord(path=path_str)
        session.add(record)

    record.size_bytes = stat.st_size
    record.mtime = mtime
    record.mime_type = mime_type
    record.scanned_at = scanned_at
    record.extra = json.dumps({"proposed_filename": proposed_name})

    proposed_changes.append(
        {
            "original_path": path_str,
            "proposed_filename": proposed_name,
            "file_size_bytes": stat.st_size,
        }
    )


@dataclass(frozen=True)
class CrawlResult:
    files_scanned: int
    report_path: Path | None


def crawl_directory(
    root: Path,
    *,
    dry_run: bool = True,
    write_report: bool = True,
) -> CrawlResult:
    """Walk *root*, index files in the database, and optionally write an audit report.

    *dry_run* preserves the original safety contract: no on-disk renames. When
    rename support exists, only ``dry_run=False`` will apply changes.
    """
    if not dry_run:
        raise RuntimeError("On-disk renames are not implemented; use dry-run mode.")

    root = root.resolve()
    proposed_changes: list[dict[str, object]] = []
    scanned_at = datetime.now(UTC)

    Base.metadata.create_all(get_engine())

    with session_scope() as session:
        for dirpath, dirs, files in os.walk(root):
            for name in _prune_walk_dirs(dirs):
                _index_path(session, Path(dirpath) / name, scanned_at, proposed_changes)

            for name in files:
                if _should_skip(name):
                    continue
                _index_path(session, Path(dirpath) / name, scanned_at, proposed_changes)

    report_path: Path | None = None
    if write_report:
        report_path = data_dir() / AUDIT_REPORT_NAME
        payload = {
            "audit_timestamp": scanned_at.isoformat(),
            "root": str(root),
            "dry_run": dry_run,
            "total_files_scanned": len(proposed_changes),
            "proposed_changes": proposed_changes,
        }
        report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    return CrawlResult(files_scanned=len(proposed_changes), report_path=report_path)
