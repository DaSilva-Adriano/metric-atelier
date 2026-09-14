"""Video workspace: runs table, notes, and publication charts."""

from __future__ import annotations

from typing import Any

from nicegui import app, ui

from metric_atelier.charts import auto_subtitle, figure_for_type, visible_runs
from metric_atelier.export import (
    export_dir,
    runs_to_csv,
    runs_to_markdown,
    stamp_name,
    write_dataset_json,
    write_figure,
)
from metric_atelier.grouping import (
    default_chart_title,
    friendly_run_name,
    method_series_key,
    method_short_label,
    reference_label,
    sort_runs,
)
from metric_atelier.metrics import (
    ALL_METRICS_KEY,
    CATALOG,
    SECONDARY_METRICS,
    column_label,
    flag_anomalous_runs,
    format_metric,
    resolve_metric_choice,
    threshold_status,
)
from metric_atelier.models import (
    CHART_ORDER_LABELS,
    CHART_TYPE_LABELS,
    UNASSIGNED_VIDEO_ID,
    AppSettings,
    RunDTO,
)
from metric_atelier.store import get_store
from metric_atelier.theme import method_color
from metric_atelier.views.common import (
    app_frame,
    confirm_dialog,
    format_fps,
    metric_cell,
    metric_filter_chips,
    open_import_dialog,
)


@ui.page("/video/{video_id}")
def video_page(video_id: str) -> None:
    store = get_store()
    if store.get_video(video_id) is None:
        with app_frame("library"):
            ui.label("This video is not in the library.").classes("ma-title")
            ui.link("Back to library", "/")
        return
    with app_frame("library") as settings:
        _workspace(video_id, settings)


@ui.refreshable
def _workspace(video_id: str, settings: AppSettings) -> None:
    store = get_store()
    video = store.get_video(video_id)
    if video is None:
        ui.label("Missing video.")
        return
    settings = store.get_settings()
    all_runs = store.list_runs(video_id, include_hidden=True, include_deleted=False)
    highlight = set(app.storage.user.get("highlight_runs") or [])
    include_hidden = {"on": settings.reveal_hidden}
    hidden_methods: set[str] = set()
    hidden_resolutions: set[str] = set()
    selected: list[str] = []
    chart_type = {"value": settings.default_chart_type}
    chart_order = {"value": settings.default_chart_order}
    group_by = {"value": "resolution"}
    scatter_x = {"value": "psnr_y"}
    scatter_y = {"value": "vmaf"}
    chart_metric = {"value": ALL_METRICS_KEY}
    baseline = {"value": "bicubic"}
    include_hidden_charts = {"on": False}

    flags = flag_anomalous_runs(
        [{"run_id": r.run_id, "metrics": r.metrics_dict(), "errors": r.errors} for r in all_runs]
    )

    with ui.row().classes("w-full items-start justify-between gap-4"):
        with ui.column().classes("gap-2 flex-grow"):
            ui.label("Video").classes("ma-kicker")
            name_in = (
                ui.input(value=video.display_name)
                .classes("text-2xl w-full")
                .props("borderless")
                .style("font-family: var(--ma-serif); font-size: 2rem; font-weight: 600")
            )

            def save_name(e) -> None:
                store.update_video(video_id, display_name=e.value or video.display_name)

            name_in.on_value_change(save_name)
            if reference_label(video):
                ui.label(reference_label(video)).classes("ma-meta")
            notes = (
                ui.textarea(value=video.notes, placeholder="Notes (markdown)")
                .classes("w-full edit-chrome")
                .props("outlined autogrow")
            )
            notes.on_value_change(lambda e: store.update_video(video_id, notes=e.value or ""))
            if video.notes and settings.presentation_mode:
                ui.markdown(video.notes).classes("ma-note-preview")
            tags_in = (
                ui.input(
                    value=", ".join(video.tags or []),
                    placeholder="tags, comma separated",
                )
                .classes("w-full edit-chrome")
                .props("dense outlined")
            )
            tags_in.on_value_change(
                lambda e: store.update_video(
                    video_id,
                    tags=[part.strip() for part in (e.value or "").split(",") if part.strip()],
                )
            )
        with ui.row().classes("edit-chrome gap-2"):
            ui.button(
                "Import",
                icon="file_upload",
                on_click=lambda: open_import_dialog(
                    force_video_id=video_id, on_done=lambda: _workspace.refresh()
                ),
            ).props("unelevated")
            if video_id != UNASSIGNED_VIDEO_ID:
                ui.button(
                    "Delete video",
                    icon="delete",
                    on_click=lambda: _delete_this_video(),
                ).props("flat color=negative")

    methods: list[str] = []
    seen_methods: set[str] = set()
    for run in all_runs:
        key = method_series_key(run, settings)
        if key != "unknown" and key not in seen_methods:
            seen_methods.add(key)
            methods.append(key)
    resolutions = sorted(
        {r.resolution_label for r in all_runs},
        key=lambda x: settings.resolution_order.index(x) if x in settings.resolution_order else 99,
    )

    with ui.row().classes("ma-toolbar w-full"):
        hidden_n = sum(1 for r in all_runs if r.hidden)
        show_hidden = ui.switch(f"Hidden ({hidden_n})", value=include_hidden["on"])
        ui.button("Hide selected", on_click=lambda: _hide_selected()).props("flat dense").classes(
            "edit-chrome"
        )
        ui.button("Delete selected", on_click=lambda: _delete_selected()).props(
            "flat dense color=negative"
        ).classes("edit-chrome")
        ui.button("Sort by resolution", on_click=lambda: _sort("resolution")).props("outline dense")
        ui.button("Sort by method", on_click=lambda: _sort("method")).props("outline dense")
        ui.button("Sort by VMAF", on_click=lambda: _sort("vmaf")).props("outline dense")
        with ui.button("Columns", icon="view_column").props("flat dense").classes("edit-chrome"):
            with ui.menu(), ui.column().classes("p-2"):
                for key, spec in CATALOG.items():
                    ui.checkbox(
                        spec.short_label, value=key in settings.visible_columns
                    ).on_value_change(lambda e, k=key: _toggle_column(k, e.value))
        ui.button("Export figure", on_click=lambda: _export_figure()).props("outline dense")
        ui.button("Export table", on_click=lambda: _export_table()).props("outline dense")
        ui.button("Export JSON", on_click=lambda: _export_json()).props("outline dense")

    with ui.row().classes("gap-2 flex-wrap mb-2"):
        ui.label("Methods").classes("ma-hint self-center")
        for method in methods:
            ui.chip(
                method_short_label(method, settings),
                selectable=True,
                selected=True,
                color=None,
                on_selection_change=lambda e, m=method: (
                    hidden_methods.discard(m) if e.value else hidden_methods.add(m),
                    refresh_table_and_charts(),
                ),
            ).props("outline dense").style(f"border-color: {method_color(method, settings)}")
        ui.label("Resolution").classes("ma-hint self-center ml-2")
        for res in resolutions:
            ui.chip(
                res,
                selectable=True,
                selected=True,
                color=None,
                on_selection_change=lambda e, r=res: (
                    hidden_resolutions.discard(r) if e.value else hidden_resolutions.add(r),
                    refresh_table_and_charts(),
                ),
            ).props("outline dense")

    table_host = ui.column().classes("w-full")
    chart_host = ui.column().classes("w-full mt-6")
    table_ref: dict[str, Any] = {"table": None}
    detail = ui.dialog()
    with detail, ui.card().classes("w-[32rem] max-w-[94vw] max-h-[90vh] overflow-auto"):
        detail_host = ui.column().classes("w-full gap-2")

    def current_runs() -> list[RunDTO]:
        return visible_runs(
            all_runs,
            include_hidden=include_hidden["on"],
            hidden_methods=hidden_methods,
            hidden_resolutions=hidden_resolutions,
            settings=settings,
        )

    def refresh_table_and_charts() -> None:
        _render_table()
        _render_charts()

    def _render_table() -> None:
        table_host.clear()
        runs = current_runs()
        rows = []
        for run in runs:
            row = {
                "run_id": run.run_id,
                "name": friendly_run_name(run, settings),
                "method": method_short_label(run.method, settings, method_raw=run.method_raw),
                "resolution": run.resolution_label,
                "fps": format_fps(run.fps),
                "status": _status_label(run, flags, settings),
                "notes": "✎" if run.notes else "",
                "raw": run.raw_name if settings.show_raw_filenames else "",
                "hidden": run.hidden,
            }
            for key in list(settings.hero_metrics) + list(SECONDARY_METRICS):
                row[key] = metric_cell(run, key, settings)
                row[f"_{key}"] = run.metric(key)
            rows.append(row)

        columns = [
            {"name": "name", "label": "Name", "field": "name", "align": "left", "sortable": True},
            {"name": "method", "label": "Method", "field": "method", "sortable": True},
            {"name": "resolution", "label": "Res", "field": "resolution", "sortable": True},
            {"name": "fps", "label": "fps", "field": "fps", "sortable": True},
        ]
        visible_set = set(settings.visible_columns)
        for key in settings.hero_metrics:
            if key in visible_set or key in settings.hero_metrics:
                columns.append(
                    {
                        "name": key,
                        "label": column_label(key),
                        "field": key,
                        "sortable": True,
                        "align": "right",
                        ":sort": (
                            f"(a, b, rowA, rowB) => (rowA._{key} ?? -9999) - (rowB._{key} ?? -9999)"
                        ),
                    }
                )
        if "status" in visible_set:
            columns.append({"name": "status", "label": "Flags", "field": "status"})
        if "notes" in visible_set:
            columns.append({"name": "notes", "label": "", "field": "notes"})
        if settings.show_raw_filenames:
            columns.append(
                {"name": "raw", "label": "Raw filename", "field": "raw", "align": "left"}
            )

        with table_host:
            if not runs:
                ui.label("No visible runs. Import a CSV or show hidden rows.").classes("ma-hint")
                return
            table = (
                ui.table(
                    columns=columns,
                    rows=rows,
                    row_key="run_id",
                    selection="multiple",
                    pagination=None,
                )
                .classes("w-full ma-table")
                .props("dense flat")
            )
            for run in runs:
                if run.run_id in highlight:
                    pass

            def on_select(e) -> None:
                selected.clear()
                selected.extend(row["run_id"] for row in (e.selection or []))

            table.on_select(on_select)
            table_ref["table"] = table
            with table.add_slot("body-cell-name"):
                with table.cell("name"):
                    ui.button().props(":label=props.value flat dense no-caps").on(
                        "click",
                        js_handler="() => emit(props.row.run_id)",
                        handler=lambda e: _open_detail(e.args),
                    )

    def _open_detail(run_id: str) -> None:
        if isinstance(run_id, dict):
            run_id = run_id.get("run_id") or ""
        run = store.get_run(str(run_id))
        if run is None:
            return
        detail_host.clear()
        with detail_host:
            ui.label(friendly_run_name(run, settings)).style(
                "font-family: var(--ma-serif); font-size: 1.3rem; font-weight: 600"
            )
            ui.label(run.raw_name).classes("ma-meta")
            disp = ui.input("Friendly name", value=run.display_name or "").classes("w-full")
            disp.on_value_change(
                lambda e, rid=run_id: store.update_run(rid, display_name=e.value or None)
            )
            ui.button(
                "Reset friendly name",
                on_click=lambda rid=run_id: (
                    store.update_run(rid, display_name=None) or _workspace.refresh()
                ),
            ).props("flat dense")
            notes = ui.textarea("Notes", value=run.notes).classes("w-full").props("autogrow")
            notes.on_value_change(lambda e, rid=run_id: store.update_run(rid, notes=e.value or ""))
            ui.switch("Hidden", value=run.hidden).on_value_change(
                lambda e, rid=run_id: store.set_hidden([rid], bool(e.value)) or _workspace.refresh()
            )
            videos = {v.video_id: v.display_name for v in store.list_videos()}
            ui.select(videos, value=run.video_id, label="Move to video").classes(
                "w-full"
            ).on_value_change(
                lambda e, rid=run_id: store.move_run(rid, e.value) or _workspace.refresh()
            )
            ui.separator()
            ui.label("Metrics (read-only)").classes("text-sm uppercase tracking-wide")
            for key, spec in CATALOG.items():
                value = format_metric(key, run.metric(key), decimals=settings.decimal_places)
                status = threshold_status(key, run.metric(key), settings.metric_thresholds)
                with ui.row().classes("w-full justify-between"):
                    ui.label(f"{spec.short_label} {spec.arrow}").classes("ma-meta")
                    ui.label(value).classes("ma-num ma-fail" if status == "fail" else "ma-num")
            ui.separator()
            ui.label("Source").classes("text-sm uppercase tracking-wide")
            ui.label(f"CSV: {run.source_csv}").classes("ma-meta")
            ui.label(f"Path: {run.path or '—'}").classes("ma-meta")
            if run.leftovers:
                ui.label(f"Leftovers: {run.leftovers}").classes("ma-meta")
            if run.warnings:
                ui.label("Warnings").classes("ma-chip warn")
                for item in run.warnings:
                    ui.label(item).classes("ma-meta")
            if run.errors:
                ui.label("Errors").classes("ma-chip danger")
                for item in run.errors:
                    ui.label(item).classes("ma-meta")
            extra_flags = flags.get(run.run_id) or []
            for item in extra_flags:
                ui.label(item).classes("ma-chip warn")
            with ui.row().classes("mt-4 edit-chrome"):
                ui.button(
                    "Delete row",
                    on_click=lambda rid=str(run_id): _confirm_purge([rid], close=detail),
                ).props("flat dense color=negative")
            ui.button("Close", on_click=detail.close).props("flat")
        detail.open()

    def _render_charts() -> None:
        chart_host.clear()
        chart_runs = visible_runs(
            all_runs,
            include_hidden=include_hidden_charts["on"],
            hidden_methods=hidden_methods,
            hidden_resolutions=hidden_resolutions,
            settings=settings,
        )
        with chart_host:
            ui.label("Figures").classes("ma-kicker")
            title_in = ui.input(
                "Chart title",
                value=video.chart_title or default_chart_title(video),
            ).classes("w-full")
            title_in.on_value_change(
                lambda e: store.update_video(video_id, chart_title=e.value or None)
            )
            subtitle = auto_subtitle(chart_runs, video, settings)
            ui.label(subtitle).classes("ma-meta")
            with ui.row().classes("gap-2 items-end flex-wrap"):
                ui.select(
                    CHART_TYPE_LABELS,
                    value=chart_type["value"],
                    label="Chart",
                ).classes("w-64").on_value_change(
                    lambda e: chart_type.update(value=e.value) or _render_charts()
                )
                ui.select(
                    CHART_ORDER_LABELS,
                    value=chart_order["value"],
                    label="Order",
                ).classes("w-56").on_value_change(
                    lambda e: chart_order.update(value=e.value) or _render_charts()
                )
                if chart_type["value"] == "grouped_bar":
                    ui.select(
                        {"resolution": "Group by resolution", "method": "Group by method"},
                        value=group_by["value"],
                        label="Group by",
                    ).classes("w-52").on_value_change(
                        lambda e: group_by.update(value=e.value) or _render_charts()
                    )
                if chart_type["value"] == "scatter":
                    metric_options = {k: CATALOG[k].short_label for k in settings.hero_metrics}
                    ui.select(
                        metric_options,
                        value=scatter_x["value"]
                        if scatter_x["value"] in metric_options
                        else settings.hero_metrics[1]
                        if len(settings.hero_metrics) > 1
                        else "psnr_y",
                        label="X metric",
                    ).classes("w-40").on_value_change(
                        lambda e: scatter_x.update(value=e.value) or _render_charts()
                    )
                    ui.select(
                        metric_options,
                        value=scatter_y["value"]
                        if scatter_y["value"] in metric_options
                        else settings.hero_metrics[0],
                        label="Y metric",
                    ).classes("w-40").on_value_change(
                        lambda e: scatter_y.update(value=e.value) or _render_charts()
                    )
                ui.select(
                    {m: method_short_label(m, settings) for m in methods} or {"bicubic": "Bicubic"},
                    value=baseline["value"]
                    if baseline["value"] in methods
                    else (methods[0] if methods else "bicubic"),
                    label="Baseline",
                ).classes("w-40").on_value_change(
                    lambda e: baseline.update(value=e.value) or _render_charts()
                )
                ui.switch(
                    "Include hidden in charts", value=include_hidden_charts["on"]
                ).on_value_change(
                    lambda e: include_hidden_charts.update(on=e.value) or _render_charts()
                )
            if chart_type["value"] != "scatter":
                with ui.row().classes("gap-1 flex-wrap items-center"):
                    metric_filter_chips(settings.hero_metrics, chart_metric, _render_charts)
            ui.label(
                "Metric: All metrics keeps one panel per metric. Pick VMAF, PSNR, … for a full-size chart. "
                "Order applies to the category axis, or to individual bars on ranked/horizontal charts. "
                "Use table sort plus “Table / custom order” to pin a specific sequence."
            ).classes("ma-hint")
            if not chart_runs:
                ui.label("Nothing to plot. Unhide rows or clear filters.").classes("ma-hint")
                return
            fig = _make_figure(
                chart_runs, title=title_in.value or default_chart_title(video), subtitle=subtitle
            )
            ui.plotly(fig).classes("w-full").style("min-height: 520px")
            with ui.row().classes("gap-2 edit-chrome"):
                ui.button("PNG 2×", on_click=lambda: _save_fig(fig, "png")).props("outline dense")
                ui.button("SVG", on_click=lambda: _save_fig(fig, "svg")).props("outline dense")
                ui.button("PDF", on_click=lambda: _save_fig(fig, "pdf")).props("outline dense")

    def _save_fig(fig, fmt: str) -> None:
        settings_now = store.get_settings()
        path = export_dir() / stamp_name(video.display_name.replace(" ", "_"), fmt)
        try:
            write_figure(fig, path, settings_now)
        except RuntimeError as exc:
            ui.notify(str(exc), type="warning", timeout=8000)
            return
        ui.download.file(str(path))
        ui.notify(f"Wrote {path.name}", type="positive")

    def _make_figure(chart_runs, *, title: str, subtitle: str):
        return figure_for_type(
            chart_type["value"],
            chart_runs,
            settings,
            title=title,
            subtitle=subtitle,
            metrics=resolve_metric_choice(chart_metric["value"], settings.hero_metrics),
            baseline=baseline["value"],
            order=chart_order["value"],
            group_by=group_by["value"],
            scatter_x=scatter_x["value"],
            scatter_y=scatter_y["value"],
        )

    def _export_figure() -> None:
        chart_runs = visible_runs(
            all_runs,
            include_hidden=include_hidden_charts["on"],
            hidden_methods=hidden_methods,
            hidden_resolutions=hidden_resolutions,
            settings=settings,
        )
        fig = _make_figure(
            chart_runs,
            title=video.chart_title or default_chart_title(video),
            subtitle=auto_subtitle(chart_runs, video, settings),
        )
        _save_fig(fig, "png")

    def _export_table() -> None:
        runs = current_runs()
        path = export_dir() / stamp_name(video.display_name.replace(" ", "_") + "_table", "csv")
        runs_to_csv(runs, settings, path)
        md = runs_to_markdown(runs, settings)
        (path.with_suffix(".md")).write_text(md, encoding="utf-8")
        ui.download.file(str(path))
        ui.notify("Exported CSV and Markdown table.", type="positive")

    def _export_json() -> None:
        payload = store.export_dataset(video_id)
        path = export_dir() / stamp_name(video.display_name.replace(" ", "_"), "json")
        write_dataset_json(payload, path)
        ui.download.file(str(path))
        ui.notify(
            "Exported JSON with method and resolution as fields (not parsed from names).",
            type="positive",
        )

    def _selected_ids() -> list[str]:
        table = table_ref.get("table")
        ids = list(selected)
        if table is not None:
            ids = [row.get("run_id") for row in (table.selected or []) if row.get("run_id")]
        return [rid for rid in ids if rid]

    def _hide_selected() -> None:
        ids = _selected_ids()
        if not ids:
            ui.notify("Select one or more rows first.", type="warning")
            return
        store.set_hidden(ids, True)
        _workspace.refresh()

    def _delete_selected() -> None:
        ids = _selected_ids()
        if not ids:
            ui.notify("Select one or more rows first.", type="warning")
            return
        _confirm_purge(ids)

    def _confirm_purge(ids: list[str], close=None) -> None:
        n = len(ids)
        label = "this row" if n == 1 else f"{n} rows"

        def do_purge() -> None:
            if close is not None:
                close.close()
            removed = store.purge_runs(ids)
            ui.notify(
                f"Deleted {removed} run"
                f"{'' if removed == 1 else 's'}. Original CSVs were not touched."
            )
            _workspace.refresh()

        confirm_dialog(
            f"Delete {label}?",
            "This permanently removes the run from Metric Atelier. Metric values cannot be edited; "
            "delete is the only change to imported rows. Original CSV files on disk are not modified.",
            on_confirm=do_purge,
        )

    def _delete_this_video() -> None:
        def do_delete() -> None:
            n = store.delete_video(video_id)
            ui.notify(
                f"Deleted {video.display_name} ({n} run"
                f"{'' if n == 1 else 's'}). Original CSVs were not touched."
            )
            ui.navigate.to("/")

        confirm_dialog(
            f"Delete “{video.display_name}” from the library?",
            "This permanently removes the video and all of its runs from Metric Atelier. "
            "Original CSV files on disk are not modified.",
            on_confirm=do_delete,
        )

    def _sort(how: str) -> None:
        ordered = sort_runs(
            store.list_runs(video_id, include_hidden=True), how=how, settings=settings
        )
        store.apply_sort(video_id, ordered)
        _workspace.refresh()

    def _toggle_column(key: str, visible: bool) -> None:
        cols = list(settings.visible_columns)
        if visible and key not in cols:
            cols.append(key)
        if not visible and key in cols:
            cols.remove(key)
        store.update_settings(visible_columns=cols)
        _workspace.refresh()

    show_hidden.on_value_change(
        lambda e: include_hidden.update(on=e.value) or refresh_table_and_charts()
    )

    def on_key(e) -> None:
        if e.action.keydown and not e.action.repeat and str(e.key) == "h":
            _hide_selected()

    ui.keyboard(on_key=on_key, repeating=False)
    refresh_table_and_charts()


def _status_label(run: RunDTO, flags: dict[str, list[str]], settings: AppSettings) -> str:
    parts: list[str] = []
    if run.errors:
        parts.append("error")
    if run.warnings:
        parts.append("warn")
    if run.run_id in flags:
        parts.append("outlier")
    if run.hidden:
        parts.append("hidden")
    if run.metric("psnr_y") is None and run.metric("vmaf") is None:
        parts.append("incomplete")
    for key in settings.hero_metrics:
        if threshold_status(key, run.metric(key), settings.metric_thresholds) == "fail":
            spec = CATALOG.get(key)
            parts.append(f"{spec.short_label if spec else key} thresh")
    return " · ".join(parts)
