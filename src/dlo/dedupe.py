from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from dlo.config import data_dir
from dlo.crawl import _root_slug, format_file_size
from dlo.models import DuplicateGroup as DuplicateGroupModel
from dlo.models import FileRecord

MatchType = str
DEDUPE_ALGORITHM_VERSION = "1"
DEDUPE_REPORT_RETENTION = 3


@dataclass(frozen=True)
class DuplicateMatch:
    """A set of indexed files that look like duplicates under one heuristic."""

    match_type: MatchType
    key: str
    paths: tuple[str, ...]
    size_bytes: int | None = None
    mime_type: str | None = None
    duplicate_group_id: int | None = None

    @property
    def count(self) -> int:
        return len(self.paths)


@dataclass(frozen=True)
class DedupeResult:
    groups_by_type: dict[MatchType, list[DuplicateMatch]]
    report_path: Path | None
    persisted_hash_groups: int


def _basename(path: str) -> str:
    return Path(path).name


def _scope_slug(path_prefix: str | None) -> str:
    if path_prefix:
        return _root_slug(Path(path_prefix))
    return "all"


def _load_records(
    session: Session,
    *,
    path_prefix: str | None = None,
    min_size_bytes: int = 0,
) -> list[FileRecord]:
    records = list(session.scalars(select(FileRecord)).all())
    if path_prefix:
        prefix = str(Path(path_prefix).resolve())
        records = [record for record in records if record.path.startswith(prefix)]
    if min_size_bytes > 0:
        records = [record for record in records if (record.size_bytes or 0) >= min_size_bytes]
    return records


def find_same_name_duplicates(records: Iterable[FileRecord]) -> list[DuplicateMatch]:
    """Group files that share a basename but live at different paths."""
    by_name: dict[str, list[FileRecord]] = defaultdict(list)
    for record in records:
        by_name[_basename(record.path).lower()].append(record)

    groups: list[DuplicateMatch] = []
    for name, files in by_name.items():
        if len(files) < 2:
            continue
        paths = tuple(sorted({file.path for file in files}))
        if len(paths) < 2:
            continue
        groups.append(
            DuplicateMatch(
                match_type="same_name",
                key=name,
                paths=paths,
                size_bytes=files[0].size_bytes,
                mime_type=files[0].mime_type,
            )
        )
    return sorted(groups, key=lambda group: (-group.count, group.key))


def find_same_size_type_duplicates(records: Iterable[FileRecord]) -> list[DuplicateMatch]:
    """Group files with identical size and MIME type but different basenames."""
    by_key: dict[tuple[int, str], list[FileRecord]] = defaultdict(list)
    for record in records:
        if record.size_bytes is None or not record.mime_type:
            continue
        by_key[(record.size_bytes, record.mime_type)].append(record)

    groups: list[DuplicateMatch] = []
    for (size_bytes, mime_type), files in by_key.items():
        if len(files) < 2:
            continue
        basenames = {_basename(file.path).lower() for file in files}
        if len(basenames) < 2:
            continue
        paths = tuple(sorted({file.path for file in files}))
        groups.append(
            DuplicateMatch(
                match_type="same_size_type",
                key=f"{mime_type} @ {format_file_size(size_bytes)}",
                paths=paths,
                size_bytes=size_bytes,
                mime_type=mime_type,
            )
        )
    return sorted(groups, key=lambda group: (-group.count, group.key))


def find_same_hash_duplicates(records: Iterable[FileRecord]) -> list[DuplicateMatch]:
    """Group files with an identical content hash."""
    by_hash: dict[str, list[FileRecord]] = defaultdict(list)
    for record in records:
        if not record.content_hash:
            continue
        by_hash[record.content_hash].append(record)

    groups: list[DuplicateMatch] = []
    for content_hash, files in by_hash.items():
        paths = tuple(sorted({file.path for file in files}))
        if len(paths) < 2:
            continue
        groups.append(
            DuplicateMatch(
                match_type="same_hash",
                key=content_hash,
                paths=paths,
                size_bytes=files[0].size_bytes,
                mime_type=files[0].mime_type,
            )
        )
    return sorted(groups, key=lambda group: (-group.count, group.key))


def find_duplicates(
    session: Session,
    *,
    path_prefix: str | None = None,
    min_size_bytes: int = 0,
) -> dict[MatchType, list[DuplicateMatch]]:
    """Run all duplicate heuristics against indexed file records."""
    records = _load_records(session, path_prefix=path_prefix, min_size_bytes=min_size_bytes)
    return {
        "same_name": find_same_name_duplicates(records),
        "same_size_type": find_same_size_type_duplicates(records),
        "same_hash": find_same_hash_duplicates(records),
    }


def _clear_hash_group_links(session: Session, *, path_prefix: str | None) -> None:
    stmt = select(FileRecord).where(FileRecord.duplicate_group_id.isnot(None))
    if path_prefix:
        prefix = str(Path(path_prefix).resolve())
        stmt = stmt.where(FileRecord.path.startswith(prefix))
    for record in session.scalars(stmt):
        record.duplicate_group_id = None


def persist_hash_duplicate_groups(
    session: Session,
    groups: list[DuplicateMatch],
    *,
    path_prefix: str | None,
) -> dict[str, int]:
    """Upsert DB duplicate groups for hash matches and link file records."""
    _clear_hash_group_links(session, path_prefix=path_prefix)
    hash_to_group_id: dict[str, int] = {}

    for group in groups:
        db_group = session.scalar(
            select(DuplicateGroupModel).where(DuplicateGroupModel.content_hash == group.key)
        )
        if db_group is None:
            db_group = DuplicateGroupModel(content_hash=group.key, status="pending")
            session.add(db_group)
            session.flush()

        hash_to_group_id[group.key] = db_group.id
        for path in group.paths:
            record = session.scalar(select(FileRecord).where(FileRecord.path == path))
            if record is not None:
                record.duplicate_group_id = db_group.id

    return hash_to_group_id


def _attach_persisted_group_ids(
    groups: list[DuplicateMatch],
    hash_to_group_id: dict[str, int],
) -> list[DuplicateMatch]:
    enriched: list[DuplicateMatch] = []
    for group in groups:
        enriched.append(
            DuplicateMatch(
                match_type=group.match_type,
                key=group.key,
                paths=group.paths,
                size_bytes=group.size_bytes,
                mime_type=group.mime_type,
                duplicate_group_id=hash_to_group_id.get(group.key),
            )
        )
    return enriched


def build_dedupe_report_name(path_prefix: str | None, scanned_at: datetime) -> str:
    timestamp = scanned_at.strftime("%Y%m%dT%H%M%SZ")
    return f"dedupe_{_scope_slug(path_prefix)}_{timestamp}_v{DEDUPE_ALGORITHM_VERSION}.json"


def _rotate_dedupe_reports(report_dir: Path, path_prefix: str | None) -> None:
    slug = _scope_slug(path_prefix)
    pattern = f"dedupe_{slug}_*_v{DEDUPE_ALGORITHM_VERSION}.json"
    reports = sorted(report_dir.glob(pattern), key=lambda path: path.name, reverse=True)
    for stale_report in reports[DEDUPE_REPORT_RETENTION:]:
        stale_report.unlink(missing_ok=True)


def _file_entry(record: FileRecord) -> dict[str, object]:
    return {
        "path": record.path,
        "basename": _basename(record.path),
        "file_size": format_file_size(record.size_bytes or 0),
        "mime_type": record.mime_type,
        "content_hash_short": (record.content_hash or "")[:12] or None,
    }


def _group_payload(session: Session, group: DuplicateMatch) -> dict[str, object]:
    records = [
        record
        for path in group.paths
        if (record := session.scalar(select(FileRecord).where(FileRecord.path == path))) is not None
    ]
    payload: dict[str, object] = {
        "match_type": group.match_type,
        "key": group.key,
        "count": group.count,
        "file_size": format_file_size(group.size_bytes or 0)
        if group.size_bytes is not None
        else None,
        "mime_type": group.mime_type,
        "files": [_file_entry(record) for record in records],
    }
    if group.match_type == "same_hash":
        payload["content_hash"] = group.key
        payload["content_hash_short"] = group.key[:12]
        payload["duplicate_group_id"] = group.duplicate_group_id
    return payload


def write_dedupe_report(
    session: Session,
    groups_by_type: dict[MatchType, list[DuplicateMatch]],
    *,
    path_prefix: str | None,
    scanned_at: datetime,
) -> Path:
    report_dir = data_dir()
    report_path = report_dir / build_dedupe_report_name(path_prefix, scanned_at)
    duplicate_groups = [
        _group_payload(session, group)
        for match_type in ("same_hash", "same_name", "same_size_type")
        for group in groups_by_type.get(match_type, [])
    ]
    payload = {
        "dedupe_timestamp": scanned_at.isoformat(),
        "algorithm_version": DEDUPE_ALGORITHM_VERSION,
        "path_prefix": path_prefix,
        "summary": {match_type: len(groups) for match_type, groups in groups_by_type.items()},
        "duplicate_groups": duplicate_groups,
    }
    report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _rotate_dedupe_reports(report_dir, path_prefix)
    return report_path


def run_dedupe(
    session: Session,
    *,
    path_prefix: str | None = None,
    min_size_bytes: int = 0,
    write_report: bool = True,
) -> DedupeResult:
    """Find duplicates, persist hash groups to the DB, and optionally write a JSON report."""
    groups_by_type = find_duplicates(
        session,
        path_prefix=path_prefix,
        min_size_bytes=min_size_bytes,
    )
    hash_to_group_id = persist_hash_duplicate_groups(
        session,
        groups_by_type["same_hash"],
        path_prefix=path_prefix,
    )
    groups_by_type["same_hash"] = _attach_persisted_group_ids(
        groups_by_type["same_hash"],
        hash_to_group_id,
    )

    scanned_at = datetime.now(UTC)
    report_path: Path | None = None
    if write_report:
        report_path = write_dedupe_report(
            session,
            groups_by_type,
            path_prefix=path_prefix,
            scanned_at=scanned_at,
        )

    return DedupeResult(
        groups_by_type=groups_by_type,
        report_path=report_path,
        persisted_hash_groups=len(hash_to_group_id),
    )
