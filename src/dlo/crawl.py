from __future__ import annotations

import json
import mimetypes
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from dlo.config import data_dir
from dlo.db import get_engine, session_scope
from dlo.models import Base, FileRecord

MEDIA_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".mp4", ".mov"})
AUDIT_REPORT_NAME = "digital_life_audit_report.json"


def get_proposed_name(filepath: Path) -> str:
    """Suggest a staged filename from modification time and file type."""
    filename = filepath.name
    stat = filepath.stat()
    mtime = datetime.fromtimestamp(stat.st_mtime, tz=UTC)
    ext = filepath.suffix.lower()

    if ext in MEDIA_EXTENSIONS:
        timestamp = mtime.strftime("%Y-%m-%dT%H.%M.%S")
        return f"{timestamp}_StagedMedia_{filename}"

    datestamp = mtime.strftime("%Y-%m-%d")
    return f"{datestamp}_Document_{filename}"


def _should_skip(name: str) -> bool:
    return name.startswith(".")


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
        for dirpath, _dirs, files in os.walk(root):
            for name in files:
                if _should_skip(name):
                    continue

                full_path = Path(dirpath) / name
                stat = full_path.stat()
                mtime = datetime.fromtimestamp(stat.st_mtime, tz=UTC)
                proposed_name = get_proposed_name(full_path)
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
