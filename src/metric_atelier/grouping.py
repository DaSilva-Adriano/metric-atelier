"""Video identity, merge/split, friendly names, and reference labels."""

from __future__ import annotations

from collections.abc import Sequence

from metric_atelier.ingest import ParsedFilename, title_to_display
from metric_atelier.models import UNASSIGNED_VIDEO_ID, AppSettings, RunDTO, SourceVideo


def is_unassigned(video_id: str) -> bool:
    return video_id == UNASSIGNED_VIDEO_ID


def friendly_run_name(run: RunDTO, settings: AppSettings) -> str:
    if run.display_name:
        return run.display_name
    method_key = run.method or "unknown"
    method = settings.method_display_aliases.get(method_key, method_key)
    res = run.resolution_label or "unknown"
    if method_key in {"unknown", None} and res == "unknown":
        return run.raw_name
    return f"{method} {res}"


def method_short_label(method: str | None, settings: AppSettings) -> str:
    if not method:
        return "unknown"
    return settings.method_display_aliases.get(method, method)


def resolution_sort_key(label: str, order: Sequence[str]) -> tuple[int, str]:
    try:
        return order.index(label), label
    except ValueError:
        return len(order), label


def sort_runs(
    runs: list[RunDTO],
    *,
    how: str,
    settings: AppSettings,
) -> list[RunDTO]:
    order = settings.resolution_order
    if how == "resolution":
        return sorted(
            runs,
            key=lambda r: (
                resolution_sort_key(r.resolution_label, order),
                (r.method or ""),
                r.raw_name,
            ),
        )
    if how == "method":
        return sorted(
            runs,
            key=lambda r: (
                (r.method or "zzz"),
                resolution_sort_key(r.resolution_label, order),
                r.raw_name,
            ),
        )
    if how == "vmaf":
        return sorted(
            runs,
            key=lambda r: (
                r.vmaf is None,
                -(r.vmaf or 0.0),
                resolution_sort_key(r.resolution_label, order),
            ),
        )
    return sorted(runs, key=lambda r: (r.sort_index, r.raw_name))


def reference_label(video: SourceVideo) -> str:
    parts: list[str] = []
    if video.reference_width and video.reference_height:
        w, h = video.reference_width, video.reference_height
        if (w, h) == (3840, 2160) or h == 2160:
            parts.append("4K")
        else:
            parts.append(f"{w}×{h}")
    if video.reference_fps:
        fps = video.reference_fps
        parts.append(f"{int(fps) if fps == int(fps) else fps} fps")
    if video.reference_color:
        parts.append(video.reference_color.upper())
    if video.reference_bits:
        parts.append(f"{video.reference_bits}-bit")
    return " · ".join(parts)


def fill_reference_from_parsed(video: SourceVideo, parsed: ParsedFilename) -> bool:
    """Set reference fields only when empty, from the first informative parse."""
    changed = False
    if video.reference_width is None and parsed.source_width:
        video.reference_width = parsed.source_width
        changed = True
    if video.reference_height is None and parsed.source_height:
        video.reference_height = parsed.source_height
        changed = True
    if video.reference_fps is None and parsed.source_fps:
        video.reference_fps = parsed.source_fps
        changed = True
    if video.reference_color is None and parsed.source_color:
        video.reference_color = parsed.source_color
        changed = True
    if video.reference_bits is None and parsed.source_bits:
        video.reference_bits = parsed.source_bits
        changed = True
    return changed


def default_chart_title(video: SourceVideo) -> str:
    if video.chart_title:
        return video.chart_title
    ref = reference_label(video)
    if ref:
        return f"{video.display_name} — {ref}, compared to reference"
    return video.display_name


def display_from_video_id(video_id: str) -> str:
    if video_id == UNASSIGNED_VIDEO_ID:
        return "Unassigned"
    return title_to_display(video_id)
