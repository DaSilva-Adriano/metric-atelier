"""Figure and table export. Original metric CSVs are never rewritten."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import plotly.graph_objects as go

from metric_atelier.charts import aligned_compare_combos, compare_run_lookup
from metric_atelier.grouping import friendly_run_name, method_display_label, method_short_label
from metric_atelier.metrics import CATALOG, format_metric
from metric_atelier.models import AppSettings, RunDTO
from metric_atelier.store import get_store


def export_dir() -> Path:
    path = get_store().data_dir / "exports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def stamp_name(stem: str, suffix: str) -> str:
    now = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in stem)
    return f"{safe}_{now}.{suffix.lstrip('.')}"


def write_figure(
    fig: go.Figure,
    dest: Path,
    settings: AppSettings,
    *,
    width: int | None = None,
) -> Path:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    width = width or settings.export_width
    height = int(fig.layout.height or max(900, int(width * 0.62)))
    fmt = dest.suffix.lstrip(".").lower() or "png"
    scale = settings.export_scale if fmt == "png" else 1
    if settings.export_background == "white":
        fig.update_layout(paper_bgcolor="#ffffff", plot_bgcolor="#ffffff")
    fig.update_layout(width=width, height=height)
    try:
        fig.write_image(str(dest), format=fmt, width=width, height=height, scale=scale)
    except Exception as exc:  # kaleido / Chrome missing
        html_fallback = dest.with_suffix(".html")
        fig.write_html(str(html_fallback), include_plotlyjs="cdn", full_html=True)
        raise RuntimeError(
            f"Could not write {fmt.upper()} ({exc}). "
            "Install Chrome for Kaleido, or use the HTML fallback at "
            f"{html_fallback}."
        ) from exc
    return dest


def runs_to_csv(
    runs: Sequence[RunDTO],
    settings: AppSettings,
    dest: Path,
    *,
    metrics: Sequence[str] | None = None,
) -> Path:
    import csv

    keys = list(metrics or settings.hero_metrics)
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["name", "method", "resolution", "fps", *keys, "warnings", "errors", "raw_name"]
    with dest.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for run in runs:
            row = {
                "name": friendly_run_name(run, settings),
                "method": method_display_label(run.method, settings, method_raw=run.method_raw),
                "resolution": run.resolution_label,
                "fps": ""
                if run.fps is None
                else (int(run.fps) if run.fps == int(run.fps) else run.fps),
                "warnings": "; ".join(run.warnings),
                "errors": "; ".join(run.errors),
                "raw_name": run.raw_name,
            }
            for key in keys:
                row[key] = format_metric(
                    key, run.metric(key), decimals=settings.decimal_places, empty=""
                )
            writer.writerow(row)
    return dest


def runs_to_markdown(
    runs: Sequence[RunDTO],
    settings: AppSettings,
    *,
    metrics: Sequence[str] | None = None,
) -> str:
    keys = list(metrics or settings.hero_metrics)
    headers = ["Name", "Method", "Res", "fps"]
    for key in keys:
        spec = CATALOG.get(key)
        headers.append(spec.short_label if spec else key)
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for run in runs:
        fps = "" if run.fps is None else str(int(run.fps) if run.fps == int(run.fps) else run.fps)
        cells = [
            friendly_run_name(run, settings),
            method_display_label(run.method, settings, method_raw=run.method_raw) or "—",
            run.resolution_label,
            fps or "—",
        ]
        for key in keys:
            cells.append(format_metric(key, run.metric(key), decimals=settings.decimal_places))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def write_dataset_json(payload: dict[str, Any], dest: Path) -> Path:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return dest


def _json_number(value: float | None) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def comparison_payload(
    series: Mapping[str, Sequence[RunDTO]],
    settings: AppSettings,
    *,
    metrics: Sequence[str],
    contents: Sequence[Mapping[str, str]],
) -> dict[str, Any]:
    """Aligned cross-content comparison. Keys in ``series`` are display names."""
    keys = [key for key in metrics if key in CATALOG] or list(settings.hero_metrics)
    combos = aligned_compare_combos(series, settings)
    lookups = {name: compare_run_lookup(runs, settings) for name, runs in series.items()}
    name_by_id = {item["video_id"]: item["display_name"] for item in contents}
    rows: list[dict[str, Any]] = []
    for method_key, resolution in combos:
        by_content: dict[str, Any] = {}
        for item in contents:
            video_id = item["video_id"]
            display = item["display_name"]
            run = lookups.get(display, {}).get((method_key, resolution))
            if run is None:
                # series may be keyed by video_id in some callers
                run = lookups.get(video_id, {}).get((method_key, resolution))
            if run is None:
                by_content[video_id] = None
                continue
            metric_values = {
                key: _json_number(run.metric(key))
                for key in run.metrics_dict()
                if _json_number(run.metric(key)) is not None
            }
            by_content[video_id] = {
                "run_id": run.run_id,
                "name": friendly_run_name(run, settings),
                "method": method_display_label(run.method, settings, method_raw=run.method_raw),
                "method_key": method_key,
                "resolution": resolution,
                "metrics": metric_values,
            }
        rows.append(
            {
                "method": method_short_label(method_key, settings),
                "method_key": method_key,
                "resolution": resolution,
                "by_content": by_content,
            }
        )
    return {
        "version": 1,
        "kind": "metric-atelier-comparison",
        "exported_at": datetime.now(UTC).isoformat(),
        "align_on": "method+resolution",
        "metrics": list(keys),
        "contents": [
            {
                "video_id": item["video_id"],
                "display_name": item["display_name"],
            }
            for item in contents
        ],
        "rows": rows,
        "content_labels": name_by_id,
    }
