"""Cross-video comparison board."""

from __future__ import annotations

from nicegui import ui

from metric_atelier.charts import build_compare_board, visible_runs
from metric_atelier.export import export_dir, stamp_name, write_figure
from metric_atelier.metrics import column_label, format_metric
from metric_atelier.models import UNASSIGNED_VIDEO_ID
from metric_atelier.store import get_store
from metric_atelier.views.common import app_frame


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
            "Pick two to six videos. Series align on method + resolution when both exist."
        ).classes("ma-lede")

        selected: list[str] = []
        host = ui.column().classes("w-full gap-4 mt-4")

        with ui.row().classes("gap-2 flex-wrap"):
            for video in videos:

                def toggle(e, vid=video.video_id):
                    if e.value:
                        if vid not in selected and len(selected) < 6:
                            selected.append(vid)
                    elif vid in selected:
                        selected.remove(vid)
                    render()

                ui.chip(
                    video.display_name,
                    selectable=True,
                    color=None,
                    on_selection_change=toggle,
                ).props("outline")

        def render() -> None:
            host.clear()
            with host:
                if len(selected) < 2:
                    ui.label("Select at least two videos to compare.").classes("ma-hint")
                    return
                series = {}
                labels = {}
                for vid in selected:
                    video = store.get_video(vid)
                    if video is None:
                        continue
                    labels[vid] = video.display_name
                    series[video.display_name] = visible_runs(
                        store.list_runs(vid, include_hidden=False),
                        include_hidden=False,
                    )
                fig = build_compare_board(
                    series,
                    settings.hero_metrics,
                    settings,
                    title="Cross-content comparison",
                    subtitle=" · ".join(labels.values()),
                )
                ui.plotly(fig).classes("w-full").style("min-height: 640px")
                ui.button(
                    "Export PNG",
                    on_click=lambda: _export(fig),
                ).props("outline")

                rows = []
                combos: list[tuple[str, str]] = []
                for runs in series.values():
                    for run in runs:
                        pair = (run.method or "unknown", run.resolution_label)
                        if pair not in combos:
                            combos.append(pair)
                combos.sort(
                    key=lambda item: (
                        settings.resolution_order.index(item[1])
                        if item[1] in settings.resolution_order
                        else 99,
                        item[0],
                    )
                )
                metric = settings.hero_metrics[0] if settings.hero_metrics else "vmaf"
                for method, res in combos:
                    row = {"combo": f"{method} / {res}"}
                    for name, runs in series.items():
                        match = next(
                            (
                                r
                                for r in runs
                                if (r.method or "unknown") == method and r.resolution_label == res
                            ),
                            None,
                        )
                        row[name] = (
                            format_metric(
                                metric, match.metric(metric), decimals=settings.decimal_places
                            )
                            if match
                            else "—"
                        )
                    rows.append(row)
                columns = [
                    {
                        "name": "combo",
                        "label": column_label(metric),
                        "field": "combo",
                        "align": "left",
                    }
                ]
                for name in series:
                    columns.append({"name": name, "label": name, "field": name, "align": "right"})
                ui.table(columns=columns, rows=rows, row_key="combo").classes("w-full").props(
                    "dense flat"
                )

        def _export(fig) -> None:
            path = export_dir() / stamp_name("compare", "png")
            try:
                write_figure(fig, path, settings)
            except RuntimeError as exc:
                ui.notify(str(exc), type="warning", timeout=8000)
                return
            ui.download.file(str(path))

        if not videos:
            ui.label("Import at least two videos, then come back.").classes("ma-hint")
        else:
            render()
