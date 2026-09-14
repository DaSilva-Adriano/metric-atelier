"""Cross-video comparison board."""

from __future__ import annotations

from nicegui import ui

from metric_atelier.charts import (
    aligned_compare_combos,
    build_compare_board,
    compare_run_lookup,
    visible_runs,
)
from metric_atelier.export import (
    comparison_payload,
    export_dir,
    stamp_name,
    write_dataset_json,
    write_figure,
)
from metric_atelier.grouping import method_short_label
from metric_atelier.metrics import (
    ALL_METRICS_KEY,
    column_label,
    format_metric,
    resolve_metric_choice,
)
from metric_atelier.models import UNASSIGNED_VIDEO_ID
from metric_atelier.store import get_store
from metric_atelier.views.common import app_frame, metric_filter_chips


@ui.page("/compare")
def compare_page() -> None:
    with app_frame("compare") as settings:
        store = get_store()
        videos = [
            v
            for v in store.list_video_summaries()
            if v.video_id != UNASSIGNED_VIDEO_ID and v.n_runs
        ]
        ui.label("Compare").classes("ma-kicker")
        ui.label("Across contents").classes("ma-title")
        ui.label(
            "Pick two or more videos. Series align on method + resolution when both exist. "
            "Choose All metrics or a single one — same control as on a video page."
        ).classes("ma-lede")

        selected: list[str] = []
        metric_sel = {"value": ALL_METRICS_KEY}
        video_options = {video.video_id: video.display_name for video in videos}

        with ui.row().classes("w-full items-end gap-3 flex-wrap mt-2"):
            picker = (
                ui.select(
                    video_options,
                    multiple=True,
                    value=[],
                    label="Contents",
                )
                .classes("min-w-[18rem] max-w-xl flex-grow")
                .props("use-chips dense options-dense")
            )
            ui.button("Select all", on_click=lambda: _select_all()).props("flat dense")
            ui.button("Clear", on_click=lambda: _clear()).props("flat dense")
        host = ui.column().classes("w-full gap-4 mt-4")

        def _select_all() -> None:
            ids = list(video_options)
            selected.clear()
            selected.extend(ids)
            picker.value = ids
            render()

        def _clear() -> None:
            selected.clear()
            picker.value = []
            render()

        def on_pick(e) -> None:
            selected.clear()
            values = e.value or []
            if isinstance(values, str):
                values = [values]
            selected.extend(str(item) for item in values if item)
            render()

        picker.on_value_change(on_pick)

        def _series_and_contents() -> tuple[dict, list[dict[str, str]]]:
            series: dict[str, list] = {}
            contents: list[dict[str, str]] = []
            for vid in selected:
                video = store.get_video(vid)
                if video is None:
                    continue
                contents.append({"video_id": vid, "display_name": video.display_name})
                series[video.display_name] = visible_runs(
                    store.list_runs(vid, include_hidden=False),
                    include_hidden=False,
                )
            return series, contents

        def render() -> None:
            host.clear()
            with host:
                with ui.row().classes("gap-1 flex-wrap items-center"):
                    metric_filter_chips(settings.hero_metrics, metric_sel, render)
                if len(selected) < 2:
                    ui.label("Select at least two videos to compare.").classes("ma-hint")
                    return
                series, contents = _series_and_contents()
                if len(series) < 2:
                    ui.label("Select at least two videos to compare.").classes("ma-hint")
                    return
                metrics = resolve_metric_choice(metric_sel["value"], settings.hero_metrics)
                subtitle = " · ".join(item["display_name"] for item in contents)
                fig = build_compare_board(
                    series,
                    metrics,
                    settings,
                    title="Cross-content comparison",
                    subtitle=subtitle,
                )
                ui.plotly(fig).classes("w-full").style("min-height: 640px")
                with ui.row().classes("gap-2"):
                    ui.button(
                        "Export PNG",
                        on_click=lambda: _export_png(fig),
                    ).props("outline")
                    ui.button(
                        "Export JSON",
                        on_click=lambda: _export_json(),
                    ).props("outline")

                _render_table(series, contents, metrics)

        def _render_table(series, contents, metrics) -> None:
            combos = aligned_compare_combos(series, settings)
            lookups = {name: compare_run_lookup(runs, settings) for name, runs in series.items()}
            show_metric_col = len(metrics) > 1
            rows: list[dict] = []
            for method, res in combos:
                method_label = method_short_label(method, settings)
                combo = f"{method_label} / {res}"
                for metric in metrics:
                    row: dict = {
                        "combo": combo,
                        "metric": column_label(metric),
                        "row_key": f"{method}|{res}|{metric}",
                    }
                    for item in contents:
                        name = item["display_name"]
                        match = lookups.get(name, {}).get((method, res))
                        row[item["video_id"]] = (
                            format_metric(
                                metric,
                                match.metric(metric),
                                decimals=settings.decimal_places,
                            )
                            if match
                            else "—"
                        )
                    rows.append(row)
            columns = [
                {
                    "name": "combo",
                    "label": "Method / res",
                    "field": "combo",
                    "align": "left",
                }
            ]
            if show_metric_col:
                columns.append(
                    {
                        "name": "metric",
                        "label": "Metric",
                        "field": "metric",
                        "align": "left",
                    }
                )
            else:
                columns[0]["label"] = column_label(metrics[0]) if metrics else "Method / res"
            for item in contents:
                columns.append(
                    {
                        "name": item["video_id"],
                        "label": item["display_name"],
                        "field": item["video_id"],
                        "align": "right",
                    }
                )
            ui.table(columns=columns, rows=rows, row_key="row_key").classes("w-full").props(
                "dense flat"
            )

        def _export_png(fig) -> None:
            path = export_dir() / stamp_name("compare", "png")
            try:
                write_figure(fig, path, settings)
            except RuntimeError as exc:
                ui.notify(str(exc), type="warning", timeout=8000)
                return
            ui.download.file(str(path))

        def _export_json() -> None:
            if len(selected) < 2:
                ui.notify("Select at least two videos first.", type="warning")
                return
            series, contents = _series_and_contents()
            metrics = resolve_metric_choice(metric_sel["value"], settings.hero_metrics)
            payload = comparison_payload(series, settings, metrics=metrics, contents=contents)
            names = "_".join(item["display_name"].replace(" ", "_") for item in contents[:4])
            path = export_dir() / stamp_name(f"compare_{names}", "json")
            write_dataset_json(payload, path)
            ui.download.file(str(path))
            ui.notify(f"Exported comparison JSON ({path.name}).", type="positive")

        if not videos:
            ui.label("Import at least two videos, then come back.").classes("ma-hint")
        else:
            render()
