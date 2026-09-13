"""Video identity, merge/split, friendly names, and reference labels."""

from __future__ import annotations

import re
from collections.abc import Sequence

from metric_atelier.ingest import KNOWN_METHODS, ParsedFilename, title_to_display
from metric_atelier.models import UNASSIGNED_VIDEO_ID, AppSettings, RunDTO, SourceVideo


def is_unassigned(video_id: str) -> bool:
    return video_id == UNASSIGNED_VIDEO_ID


def known_method_stems(settings: AppSettings | None = None) -> set[str]:
    stems = {key.lower() for key in KNOWN_METHODS}
    stems.update(value.lower() for value in KNOWN_METHODS.values())
    if settings is not None:
        stems.update(key.lower() for key in settings.method_order)
        stems.update(key.lower() for key in settings.method_display_aliases)
        stems.update(key.lower() for key in (settings.extra_method_aliases or {}))
        stems.update(str(value).lower() for value in (settings.extra_method_aliases or {}).values())
    stems.discard("")
    return stems


def registered_method_stem(
    method: str | None,
    method_raw: str | None,
    settings: AppSettings | None = None,
) -> str | None:
    key = (method or "").lower()
    raw = (method_raw or method or "").lower()
    candidates = [
        stem
        for stem in known_method_stems(settings)
        if key == stem or raw == stem or raw.startswith(stem + "_")
    ]
    if not candidates:
        return None
    return max(candidates, key=len)


def method_display_label(
    method: str | None,
    settings: AppSettings,
    *,
    method_raw: str | None = None,
) -> str:
    """Label shown in the UI.

    Registered names that contain ``_`` (e.g. ANIMEJANAI_BAL) are the full display
    name. An extra unregistered tail (ANIMEJANAI_BAL_V3) is hidden unless
    ``show_full_method_name`` is on. Unregistered ``xxxxx_yyyyy`` uses the first
    part as the assumed display name unless the full-name toggle is on.
    """
    if not method and not method_raw:
        return "unknown"
    raw = (method_raw or method or "").strip()
    aliases = settings.method_display_aliases
    stem = registered_method_stem(method, method_raw, settings)

    def aliased(token: str) -> str:
        return aliases.get(token.lower(), token)

    if stem:
        base = aliased(stem)
        if not settings.show_full_method_name:
            return base
        extra = ""
        raw_low = raw.lower()
        if raw_low.startswith(stem + "_"):
            extra = raw[len(stem) + 1 :]
        elif raw_low != stem and raw_low.startswith(stem):
            extra = raw[len(stem) :].lstrip("_-")
        return f"{base}_{extra}" if extra else base

    parts = [part for part in re.split(r"_+", raw) if part]
    if not parts:
        return aliased(raw or "unknown")
    if settings.show_full_method_name:
        return aliased(parts[0]) + ("_" + "_".join(parts[1:]) if len(parts) > 1 else "")
    return aliased(parts[0])


def method_series_key(run: RunDTO, settings: AppSettings) -> str:
    if settings.show_full_method_name:
        return (run.method_raw or run.method or "unknown").lower()
    return (run.method or "unknown").lower()


def friendly_run_name(run: RunDTO, settings: AppSettings) -> str:
    if run.display_name:
        return run.display_name
    method_key = run.method or "unknown"
    method = method_display_label(run.method, settings, method_raw=run.method_raw)
    res = run.resolution_label or "unknown"
    if method_key in {"unknown", None} and res == "unknown":
        return run.raw_name
    return f"{method} {res}"


def method_short_label(
    method: str | None, settings: AppSettings, *, method_raw: str | None = None
) -> str:
    if not method and not method_raw:
        return "unknown"
    return method_display_label(method, settings, method_raw=method_raw or method)


def resolution_sort_key(label: str, order: Sequence[str]) -> tuple[int, str]:
    try:
        return order.index(label), label
    except ValueError:
        return len(order), label


def method_sort_key(method: str | None, order: Sequence[str]) -> tuple[int, str]:
    key = method or "unknown"
    try:
        return order.index(key), key
    except ValueError:
        return len(order), key


def sort_runs(
    runs: list[RunDTO],
    *,
    how: str,
    settings: AppSettings,
    metric: str = "vmaf",
) -> list[RunDTO]:
    order = settings.resolution_order
    methods = list(settings.method_order or [])
    if how == "resolution":
        return sorted(
            runs,
            key=lambda r: (
                resolution_sort_key(r.resolution_label, order),
                method_sort_key(r.method, methods),
                r.raw_name,
            ),
        )
    if how == "method":
        return sorted(
            runs,
            key=lambda r: (
                method_sort_key(r.method, methods),
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
    if how == "value_asc":
        return sorted(
            runs,
            key=lambda r: (
                r.metric(metric) is None,
                r.metric(metric) if r.metric(metric) is not None else 0.0,
                r.sort_index,
            ),
        )
    if how == "value_desc":
        return sorted(
            runs,
            key=lambda r: (
                r.metric(metric) is None,
                -(r.metric(metric) if r.metric(metric) is not None else 0.0),
                r.sort_index,
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
