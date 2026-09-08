"""SQLite persistence for annotations and imported metric snapshots."""

from __future__ import annotations

import os
import shutil
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func
from sqlmodel import Session, SQLModel, create_engine, select

from metric_atelier.grouping import fill_reference_from_parsed, reference_label
from metric_atelier.ingest import (
    CsvSource,
    ImportPreview,
    ImportResult,
    ParsedRow,
    ParserContext,
    PreviewRow,
    apply_parser_context,
    collect_csv_paths,
    file_fingerprint,
    make_path_key,
    make_run_id,
    parse_csv_bytes,
)
from metric_atelier.metrics import KNOWN_METRIC_COLUMNS
from metric_atelier.models import (
    METRIC_FIELD_NAMES,
    UNASSIGNED_VIDEO_ID,
    AppSettings,
    ImportedFile,
    RunDTO,
    RunRecord,
    SettingsRow,
    SourceVideo,
    VideoSummary,
)

_STORE: Store | None = None


def _now() -> datetime:
    return datetime.now(UTC)


class Store:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "imports").mkdir(exist_ok=True)
        (self.data_dir / "exports").mkdir(exist_ok=True)
        self.db_path = self.data_dir / "atelier.sqlite"
        self.engine = create_engine(
            f"sqlite:///{self.db_path.as_posix()}",
            connect_args={"check_same_thread": False},
            echo=False,
        )
        SQLModel.metadata.create_all(self.engine)
        self._ensure_unassigned()
        self._ensure_settings()

    def session(self) -> Session:
        return Session(self.engine)

    def parser_context(self) -> ParserContext:
        settings = self.get_settings()
        return ParserContext(
            extra_method_aliases=settings.extra_method_aliases,
            identity_rules=settings.identity_rules,
            extra_parser_regexes=settings.extra_parser_regexes,
        )

    def get_settings(self) -> AppSettings:
        with self.session() as session:
            row = session.get(SettingsRow, 1)
            payload = row.payload if row else {}
            return AppSettings.model_validate(payload or {})

    def save_settings(self, settings: AppSettings) -> AppSettings:
        payload = settings.model_dump(mode="json")
        with self.session() as session:
            row = session.get(SettingsRow, 1)
            if row is None:
                row = SettingsRow(id=1, payload=payload)
                session.add(row)
            else:
                row.payload = payload
                session.add(row)
            session.commit()
        return settings

    def update_settings(self, **changes: Any) -> AppSettings:
        settings = self.get_settings()
        updated = settings.model_copy(update=changes)
        return self.save_settings(updated)

    def _ensure_settings(self) -> None:
        with self.session() as session:
            if session.get(SettingsRow, 1) is None:
                session.add(SettingsRow(id=1, payload=AppSettings().model_dump(mode="json")))
                session.commit()

    def _ensure_unassigned(self) -> None:
        with self.session() as session:
            if session.get(SourceVideo, UNASSIGNED_VIDEO_ID) is None:
                session.add(
                    SourceVideo(
                        video_id=UNASSIGNED_VIDEO_ID,
                        display_name="Unassigned",
                        notes="Rows that could not be grouped. Drag them onto a video, or use Move.",
                        sort_index=10_000,
                    )
                )
                session.commit()

    def get_video(self, video_id: str) -> SourceVideo | None:
        with self.session() as session:
            video = session.get(SourceVideo, video_id)
            if video is None:
                return None
            session.expunge(video)
            return video

    def list_videos(self) -> list[SourceVideo]:
        with self.session() as session:
            videos = list(session.exec(select(SourceVideo).order_by(SourceVideo.sort_index)).all())
            for video in videos:
                session.expunge(video)
            return videos

    def list_video_summaries(self) -> list[VideoSummary]:
        videos = self.list_videos()
        with self.session() as session:
            runs = list(session.exec(select(RunRecord)).all())
        by_video: dict[str, list[RunRecord]] = {}
        for run in runs:
            by_video.setdefault(run.video_id, []).append(run)

        summaries: list[VideoSummary] = []
        for video in videos:
            group = by_video.get(video.video_id, [])
            live = [r for r in group if r.deleted_at is None]
            hidden = [r for r in live if r.hidden]
            deleted = [r for r in group if r.deleted_at is not None]
            methods = sorted({r.method for r in live if r.method})
            resolutions = sorted({r.resolution_label for r in live if r.resolution_label})
            last = max((r.imported_at for r in live if r.imported_at), default=None)
            summaries.append(
                VideoSummary(
                    video_id=video.video_id,
                    display_name=video.display_name,
                    notes=video.notes,
                    tags=list(video.tags or []),
                    sort_index=video.sort_index,
                    n_runs=len(live),
                    n_hidden=len(hidden),
                    n_deleted=len(deleted),
                    n_errors=sum(1 for r in live if r.errors),
                    n_warnings=sum(1 for r in live if r.warnings),
                    methods=methods,
                    resolutions=resolutions,
                    last_import=last,
                    reference_label=reference_label(video),
                    is_unassigned=video.video_id == UNASSIGNED_VIDEO_ID,
                )
            )
        summaries.sort(
            key=lambda item: (item.is_unassigned, item.sort_index, item.display_name.lower())
        )
        return summaries

    def create_video(
        self,
        video_id: str,
        display_name: str,
        *,
        notes: str = "",
        tags: list[str] | None = None,
    ) -> SourceVideo:
        with self.session() as session:
            existing = session.get(SourceVideo, video_id)
            if existing is not None:
                session.expunge(existing)
                return existing
            max_index = session.exec(select(func.max(SourceVideo.sort_index))).one()
            video = SourceVideo(
                video_id=video_id,
                display_name=display_name,
                notes=notes,
                tags=tags or [],
                sort_index=(max_index or 0) + 1,
            )
            session.add(video)
            session.commit()
            session.refresh(video)
            session.expunge(video)
            return video

    def update_video(self, video_id: str, **fields: Any) -> SourceVideo | None:
        with self.session() as session:
            video = session.get(SourceVideo, video_id)
            if video is None:
                return None
            for key, value in fields.items():
                if hasattr(video, key):
                    setattr(video, key, value)
            video.updated_at = _now()
            session.add(video)
            session.commit()
            session.refresh(video)
            session.expunge(video)
            return video

    def reorder_videos(self, video_ids: Sequence[str]) -> None:
        with self.session() as session:
            for index, video_id in enumerate(video_ids):
                video = session.get(SourceVideo, video_id)
                if video is None or video.video_id == UNASSIGNED_VIDEO_ID:
                    continue
                video.sort_index = index
                session.add(video)
            session.commit()

    def merge_videos(self, source_id: str, target_id: str) -> SourceVideo | None:
        if source_id == target_id:
            return self.get_video(target_id)
        if source_id == UNASSIGNED_VIDEO_ID:
            raise ValueError("Cannot merge the Unassigned group away; move its runs instead.")
        with self.session() as session:
            source = session.get(SourceVideo, source_id)
            target = session.get(SourceVideo, target_id)
            if source is None or target is None:
                return None
            runs = session.exec(select(RunRecord).where(RunRecord.video_id == source_id)).all()
            for run in runs:
                run.video_id = target_id
                session.add(run)
            if not (target.notes or "").strip() and (source.notes or "").strip():
                target.notes = source.notes
            tags = list(dict.fromkeys([*(target.tags or []), *(source.tags or [])]))
            target.tags = tags
            for attr in (
                "reference_width",
                "reference_height",
                "reference_fps",
                "reference_color",
                "reference_bits",
            ):
                if getattr(target, attr) is None and getattr(source, attr) is not None:
                    setattr(target, attr, getattr(source, attr))
            target.updated_at = _now()
            session.add(target)
            session.delete(source)
            session.commit()
            session.refresh(target)
            session.expunge(target)
            return target

    def list_runs(
        self,
        video_id: str | None = None,
        *,
        include_hidden: bool = True,
        include_deleted: bool = False,
    ) -> list[RunDTO]:
        with self.session() as session:
            statement = select(RunRecord)
            if video_id is not None:
                statement = statement.where(RunRecord.video_id == video_id)
            records = list(
                session.exec(statement.order_by(RunRecord.sort_index, RunRecord.raw_name)).all()
            )
        dtos = [RunDTO.model_validate(record, from_attributes=True) for record in records]
        if not include_deleted:
            dtos = [run for run in dtos if run.deleted_at is None]
        if not include_hidden:
            dtos = [run for run in dtos if not run.hidden]
        return dtos

    def get_run(self, run_id: str) -> RunDTO | None:
        with self.session() as session:
            record = session.get(RunRecord, run_id)
            if record is None:
                return None
            return RunDTO.model_validate(record, from_attributes=True)

    def update_run(self, run_id: str, **fields: Any) -> RunDTO | None:
        forbidden = set(METRIC_FIELD_NAMES) | {"run_id", "file_hash", "row_index", "raw_name"}
        with self.session() as session:
            record = session.get(RunRecord, run_id)
            if record is None:
                return None
            for key, value in fields.items():
                if key in forbidden:
                    continue
                if hasattr(record, key):
                    setattr(record, key, value)
            session.add(record)
            session.commit()
            session.refresh(record)
            return RunDTO.model_validate(record, from_attributes=True)

    def set_hidden(self, run_ids: Iterable[str], hidden: bool) -> None:
        ids = list(run_ids)
        with self.session() as session:
            for run_id in ids:
                record = session.get(RunRecord, run_id)
                if record is None:
                    continue
                record.hidden = hidden
                session.add(record)
            session.commit()

    def soft_delete_runs(self, run_ids: Iterable[str]) -> None:
        stamp = _now()
        with self.session() as session:
            for run_id in run_ids:
                record = session.get(RunRecord, run_id)
                if record is None:
                    continue
                record.deleted_at = stamp
                session.add(record)
            session.commit()

    def restore_runs(self, run_ids: Iterable[str]) -> None:
        with self.session() as session:
            for run_id in run_ids:
                record = session.get(RunRecord, run_id)
                if record is None:
                    continue
                record.deleted_at = None
                session.add(record)
            session.commit()

    def reorder_runs(self, run_ids: Sequence[str]) -> None:
        with self.session() as session:
            for index, run_id in enumerate(run_ids):
                record = session.get(RunRecord, run_id)
                if record is None:
                    continue
                record.sort_index = index
                session.add(record)
            session.commit()

    def move_run(self, run_id: str, target_video_id: str) -> RunDTO | None:
        with self.session() as session:
            record = session.get(RunRecord, run_id)
            target = session.get(SourceVideo, target_video_id)
            if record is None or target is None:
                return None
            record.video_id = target_video_id
            session.add(record)
            session.commit()
            session.refresh(record)
            return RunDTO.model_validate(record, from_attributes=True)

    def apply_sort(self, video_id: str, ordered: Sequence[RunDTO]) -> None:
        self.reorder_runs([run.run_id for run in ordered])

    def list_imported_files(self) -> list[ImportedFile]:
        with self.session() as session:
            files = list(
                session.exec(select(ImportedFile).order_by(ImportedFile.imported_at.desc())).all()
            )
            for item in files:
                session.expunge(item)
            return files

    def delete_imported_file(self, file_hash: str) -> int:
        """Remove runs that came from this imported snapshot. Original CSVs are untouched."""
        with self.session() as session:
            runs = list(
                session.exec(select(RunRecord).where(RunRecord.file_hash == file_hash)).all()
            )
            count = len(runs)
            for run in runs:
                session.delete(run)
            imported = session.get(ImportedFile, file_hash)
            if imported is not None:
                session.delete(imported)
            session.commit()
        return count

    def preview_sources(
        self,
        sources: list[CsvSource],
        *,
        force_video_id: str | None = None,
        reimport_mode: str | None = None,
    ) -> ImportPreview:
        ctx = self.parser_context()
        settings = self.get_settings()
        mode = reimport_mode or settings.reimport_mode
        videos = {v.video_id: v for v in self.list_videos()}
        existing_ids, existing_path_keys = self._existing_keys()

        preview_rows: list[PreviewRow] = []
        for source in sources:
            rows = apply_parser_context(
                parse_csv_bytes(source.content, source_name=source.name), ctx
            )
            file_hash = file_fingerprint(source.content)
            origin = source.original_path or source.name
            for row in rows:
                if force_video_id:
                    row.parsed.video_id = force_video_id
                    row.parsed.unassigned = force_video_id == UNASSIGNED_VIDEO_ID
                run_id = make_run_id(file_hash, row.row_index, row.distorted)
                path_key = make_path_key(origin, row.row_index, row.distorted)
                status: str
                if run_id in existing_ids:
                    status = "refresh" if mode == "refresh" else "duplicate"
                elif path_key in existing_path_keys:
                    status = "refresh" if mode == "refresh" else "duplicate"
                elif row.parsed.unassigned:
                    status = "unassigned"
                else:
                    status = "new"
                if row.errors and status == "new":
                    status = "new"
                video = videos.get(row.parsed.video_id)
                display = video.display_name if video else row.parsed.display_title
                preview_rows.append(
                    PreviewRow(
                        row_index=row.row_index,
                        raw_name=row.distorted,
                        video_id=row.parsed.video_id,
                        video_display=display,
                        method=row.parsed.method,
                        resolution_label=row.parsed.resolution_label,
                        status=status,  # type: ignore[arg-type]
                        errors=row.errors,
                        warnings=row.warnings,
                        run_id=run_id,
                        path_key=path_key,
                    )
                )

        assigned = sum(
            1
            for row in preview_rows
            if row.status == "new"
            and row.video_id in videos
            and row.video_id != UNASSIGNED_VIDEO_ID
        )
        return ImportPreview(
            files=[source.name for source in sources],
            rows=preview_rows,
            n_new=sum(1 for row in preview_rows if row.status == "new"),
            n_duplicate=sum(1 for row in preview_rows if row.status == "duplicate"),
            n_refresh=sum(1 for row in preview_rows if row.status == "refresh"),
            n_assigned=assigned,
            n_unassigned=sum(1 for row in preview_rows if row.status == "unassigned"),
            n_errors=sum(1 for row in preview_rows if row.errors),
        )

    def commit_sources(
        self,
        sources: list[CsvSource],
        *,
        force_video_id: str | None = None,
        reimport_mode: str | None = None,
    ) -> ImportResult:
        ctx = self.parser_context()
        settings = self.get_settings()
        mode = reimport_mode or settings.reimport_mode
        new_ids: list[str] = []
        affected: set[str] = set()
        n_new = n_dup = n_refresh = n_unassigned = n_errors = 0

        with self.session() as session:
            existing_ids = {row[0] for row in session.exec(select(RunRecord.run_id)).all()}
            path_map = {record.path_key: record for record in session.exec(select(RunRecord)).all()}
            max_sort: dict[str, int] = {}

            for source in sources:
                rows = apply_parser_context(
                    parse_csv_bytes(source.content, source_name=source.name), ctx
                )
                file_hash = file_fingerprint(source.content)
                snapshot = self._write_snapshot(source.name, source.content)
                origin = source.original_path or str(snapshot)
                imported = session.get(ImportedFile, file_hash)
                if imported is None:
                    session.add(
                        ImportedFile(
                            file_hash=file_hash,
                            original_path=source.original_path or "",
                            snapshot_path=str(snapshot),
                            basename=source.name,
                            n_rows=len(rows),
                        )
                    )
                else:
                    imported.n_rows = len(rows)
                    imported.snapshot_path = str(snapshot)
                    session.add(imported)

                for row in rows:
                    if force_video_id:
                        row.parsed.video_id = force_video_id
                        row.parsed.unassigned = force_video_id == UNASSIGNED_VIDEO_ID
                    parsed = row.parsed
                    run_id = make_run_id(file_hash, row.row_index, row.distorted)
                    path_key = make_path_key(origin, row.row_index, row.distorted)
                    if row.errors:
                        n_errors += 1

                    record = session.get(RunRecord, run_id)
                    if record is None:
                        record = path_map.get(path_key)

                    if record is not None:
                        if mode == "refresh":
                            self._copy_metrics(record, row)
                            record.file_hash = file_hash
                            record.source_csv = origin
                            record.snapshot_path = str(snapshot)
                            record.warnings = row.warnings
                            record.errors = row.errors
                            record.extra_columns = row.extra_columns
                            record.path = row.path
                            session.add(record)
                            n_refresh += 1
                            affected.add(record.video_id)
                        else:
                            n_dup += 1
                        continue

                    video = self._get_or_create_video(session, parsed, max_sort)
                    fill_reference_from_parsed(video, parsed)
                    session.add(video)
                    sort_index = max_sort.get(video.video_id, -1) + 1
                    max_sort[video.video_id] = sort_index

                    record = RunRecord(
                        run_id=run_id,
                        path_key=path_key,
                        video_id=video.video_id,
                        raw_name=row.distorted,
                        source_csv=origin,
                        source_basename=source.name,
                        snapshot_path=str(snapshot),
                        file_hash=file_hash,
                        row_index=row.row_index,
                        batch_tag=parsed.prefix,
                        method=parsed.method,
                        method_raw=parsed.method_raw,
                        method_known=parsed.method_known,
                        resolution_label=parsed.resolution_label,
                        width=parsed.width,
                        height=parsed.height,
                        fps=parsed.fps,
                        source_width=parsed.source_width,
                        source_height=parsed.source_height,
                        source_fps=parsed.source_fps,
                        source_color=parsed.source_color,
                        source_bits=parsed.source_bits,
                        leftovers=parsed.leftovers,
                        extra_columns=row.extra_columns,
                        warnings=row.warnings,
                        errors=row.errors,
                        path=row.path,
                        hidden=False,
                        sort_index=sort_index,
                    )
                    self._copy_metrics(record, row)
                    session.add(record)
                    path_map[path_key] = record
                    existing_ids.add(run_id)
                    new_ids.append(run_id)
                    n_new += 1
                    affected.add(video.video_id)
                    if parsed.unassigned:
                        n_unassigned += 1

            session.commit()

        return ImportResult(
            n_new=n_new,
            n_duplicate=n_dup,
            n_refresh=n_refresh,
            n_unassigned=n_unassigned,
            n_errors=n_errors,
            new_run_ids=new_ids,
            affected_video_ids=sorted(affected),
        )

    def import_paths(
        self,
        paths: Sequence[Path],
        *,
        force_video_id: str | None = None,
        reimport_mode: str | None = None,
    ) -> ImportResult:
        sources: list[CsvSource] = []
        for path in paths:
            for csv_path in collect_csv_paths(Path(path)):
                sources.append(
                    CsvSource(
                        name=csv_path.name,
                        content=csv_path.read_bytes(),
                        original_path=str(csv_path.resolve()),
                    )
                )
        return self.commit_sources(
            sources, force_video_id=force_video_id, reimport_mode=reimport_mode
        )

    def export_annotations(self) -> dict[str, Any]:
        videos = self.list_videos()
        runs = self.list_runs(include_hidden=True, include_deleted=True)
        settings = self.get_settings()
        return {
            "version": 1,
            "settings": settings.model_dump(mode="json"),
            "videos": [
                {
                    "video_id": v.video_id,
                    "display_name": v.display_name,
                    "notes": v.notes,
                    "tags": v.tags,
                    "sort_index": v.sort_index,
                    "reference_width": v.reference_width,
                    "reference_height": v.reference_height,
                    "reference_fps": v.reference_fps,
                    "reference_color": v.reference_color,
                    "reference_bits": v.reference_bits,
                    "chart_title": v.chart_title,
                    "chart_caption": v.chart_caption,
                }
                for v in videos
            ],
            "runs": [
                {
                    "run_id": r.run_id,
                    "path_key": r.path_key,
                    "video_id": r.video_id,
                    "raw_name": r.raw_name,
                    "source_basename": r.source_basename,
                    "row_index": r.row_index,
                    "hidden": r.hidden,
                    "display_name": r.display_name,
                    "notes": r.notes,
                    "sort_index": r.sort_index,
                    "color": r.color,
                    "deleted_at": r.deleted_at.isoformat() if r.deleted_at else None,
                }
                for r in runs
            ],
        }

    def import_annotations(self, payload: dict[str, Any]) -> None:
        with self.session() as session:
            if "settings" in payload and isinstance(payload["settings"], dict):
                row = session.get(SettingsRow, 1)
                settings = AppSettings.model_validate(payload["settings"])
                if row is None:
                    session.add(SettingsRow(id=1, payload=settings.model_dump(mode="json")))
                else:
                    row.payload = settings.model_dump(mode="json")
                    session.add(row)
            for item in payload.get("videos") or []:
                video_id = item.get("video_id")
                if not video_id:
                    continue
                video = session.get(SourceVideo, video_id)
                if video is None:
                    video = SourceVideo(
                        video_id=video_id, display_name=item.get("display_name") or video_id
                    )
                for key in (
                    "display_name",
                    "notes",
                    "tags",
                    "sort_index",
                    "reference_width",
                    "reference_height",
                    "reference_fps",
                    "reference_color",
                    "reference_bits",
                    "chart_title",
                    "chart_caption",
                ):
                    if key in item and item[key] is not None:
                        setattr(video, key, item[key])
                session.add(video)
            for item in payload.get("runs") or []:
                record = None
                if item.get("run_id"):
                    record = session.get(RunRecord, item["run_id"])
                if record is None and item.get("path_key"):
                    record = session.exec(
                        select(RunRecord).where(RunRecord.path_key == item["path_key"])
                    ).first()
                if record is None and item.get("raw_name") is not None:
                    record = session.exec(
                        select(RunRecord).where(
                            RunRecord.raw_name == item["raw_name"],
                            RunRecord.row_index == item.get("row_index", 0),
                            RunRecord.source_basename == item.get("source_basename", ""),
                        )
                    ).first()
                if record is None:
                    continue
                for key in ("hidden", "display_name", "notes", "sort_index", "color", "video_id"):
                    if key in item:
                        setattr(record, key, item[key])
                if "deleted_at" in item:
                    value = item["deleted_at"]
                    record.deleted_at = datetime.fromisoformat(value) if value else None
                session.add(record)
            session.commit()

    def _existing_keys(self) -> tuple[set[str], set[str]]:
        with self.session() as session:
            ids = set(session.exec(select(RunRecord.run_id)).all())
            keys = set(session.exec(select(RunRecord.path_key)).all())
        return ids, keys

    def _write_snapshot(self, name: str, content: bytes) -> Path:
        safe = "".join(ch if ch.isalnum() or ch in ".-_" else "_" for ch in name)
        stamp = _now().strftime("%Y%m%d-%H%M%S-%f")
        path = self.data_dir / "imports" / f"{stamp}_{safe}"
        path.write_bytes(content)
        return path

    def _get_or_create_video(
        self,
        session: Session,
        parsed: Any,
        max_sort: dict[str, int],
    ) -> SourceVideo:
        video = session.get(SourceVideo, parsed.video_id)
        if video is not None:
            if parsed.video_id not in max_sort:
                current = session.exec(
                    select(func.max(RunRecord.sort_index)).where(
                        RunRecord.video_id == video.video_id
                    )
                ).one()
                max_sort[video.video_id] = current if current is not None else -1
            return video
        overall = session.exec(select(func.max(SourceVideo.sort_index))).one()
        video = SourceVideo(
            video_id=parsed.video_id,
            display_name=parsed.display_title or parsed.video_id,
            sort_index=(overall or 0) + 1,
        )
        session.add(video)
        session.flush()
        max_sort[video.video_id] = -1
        return video

    @staticmethod
    def _copy_metrics(record: RunRecord, row: ParsedRow) -> None:
        for key in KNOWN_METRIC_COLUMNS:
            setattr(record, key, row.metrics.get(key))
        record.lpips_label = row.labels.get("lpips_label")
        record.erqa_label = row.labels.get("erqa_label")
        record.extra_columns = row.extra_columns
        record.warnings = row.warnings
        record.errors = row.errors
        record.path = row.path


def resolve_data_dir(explicit: Path | None = None) -> Path:
    if explicit is not None:
        return Path(explicit).expanduser().resolve()
    env = os.environ.get("METRIC_ATELIER_HOME")
    if env:
        return Path(env).expanduser().resolve()
    return (Path.cwd() / "data").resolve()


def init_store(data_dir: Path | None = None) -> Store:
    global _STORE
    _STORE = Store(resolve_data_dir(data_dir))
    return _STORE


def get_store() -> Store:
    if _STORE is None:
        raise RuntimeError("Store is not initialized. Call init_store() first.")
    return _STORE


def open_directory(path: Path) -> None:
    target = Path(path)
    target.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        os.startfile(target)  # type: ignore[attr-defined]
    elif shutil.which("open"):
        os.system(f'open "{target}"')
    else:
        os.system(f'xdg-open "{target}"')
