"""Library of source videos."""

from __future__ import annotations

from nicegui import app, ui

from metric_atelier.models import UNASSIGNED_VIDEO_ID
from metric_atelier.store import get_store
from metric_atelier.theme import method_color
from metric_atelier.views.common import (
    app_frame,
    confirm_dialog,
    load_samples_into_store,
    open_import_dialog,
)


@ui.page("/")
def library_page() -> None:
    with app_frame("library") as settings:
        _library_body(settings)


@ui.refreshable
def _library_body(settings) -> None:
    store = get_store()
    videos = store.list_video_summaries()
    query = {"text": ""}
    tag = {"value": ""}
    highlight = set(app.storage.user.get("highlight_videos") or [])

    all_tags = sorted({t for v in videos for t in v.tags})

    with ui.element("div").classes("ma-top w-full"):
        with ui.column().classes("gap-1"):
            ui.label("Library").classes("ma-kicker")
            ui.label("Source videos").classes("ma-title")
            ui.label(
                "Each card is one piece of content. New CSVs with the same title merge here."
            ).classes("ma-lede")
        with ui.row().classes("edit-chrome gap-2"):
            ui.button(
                "Import CSV", icon="file_upload", on_click=lambda: open_import_dialog()
            ).props("unelevated")

    with ui.row().classes("w-full items-center gap-3 mb-4"):
        search = (
            ui.input(placeholder="Search videos")
            .props("dense outlined debounce=200")
            .classes("ma-search w-80")
        )
        tag_select = (
            ui.select(
                {"": "All tags", **{t: t for t in all_tags}},
                value="",
                label="Tag",
            )
            .classes("w-48")
            .props("dense")
        )

    host = ui.column().classes("w-full gap-3")

    def redraw() -> None:
        host.clear()
        needle = (query["text"] or "").strip().lower()
        tag_filter = tag["value"]
        visible = []
        for video in videos:
            if video.n_runs == 0 and video.video_id == UNASSIGNED_VIDEO_ID:
                continue
            hay = f"{video.display_name} {video.video_id} {' '.join(video.tags)} {video.notes}".lower()
            if needle and needle not in hay:
                continue
            if tag_filter and tag_filter not in video.tags:
                continue
            visible.append(video)
        with host:
            if not videos or all(
                v.n_runs == 0 for v in videos if v.video_id != UNASSIGNED_VIDEO_ID
            ):
                with ui.element("div").classes("ma-empty"):
                    ui.label("Import a summary CSV to start a library.").style(
                        "font-family: var(--ma-serif); font-size: 1.6rem; font-weight: 600"
                    )
                    ui.label(
                        "Drop a PSNR/SSIM/VMAF/LPIPS/ERQA summary. Rows group by content title, "
                        "not by resolution or method."
                    ).classes("ma-lede")
                    with ui.row().classes("justify-center gap-2 mt-4"):
                        ui.button("Import CSV", on_click=lambda: open_import_dialog()).props(
                            "unelevated"
                        )
                        ui.button(
                            "Load sample datasets",
                            on_click=_load_samples,
                        ).props("outline")
                return
            if not visible:
                ui.label("No videos match that search.").classes("ma-hint")
                return
            for video in visible:
                _video_card(video, highlight, settings)

    def _load_samples() -> None:
        try:
            n = load_samples_into_store()
        except FileNotFoundError as exc:
            ui.notify(str(exc), type="warning")
            return
        ui.notify(f"Loaded {n} sample runs.", type="positive")
        ui.navigate.reload()

    search.on_value_change(lambda e: query.update(text=e.value or "") or redraw())
    tag_select.on_value_change(lambda e: tag.update(value=e.value or "") or redraw())
    redraw()


def _video_card(video, highlight, settings) -> None:
    classes = "ma-card w-full"
    if video.video_id in highlight:
        classes += " highlight"
    with ui.element("div").classes(classes):
        with ui.row().classes("w-full items-start justify-between no-wrap"):
            with ui.column().classes("gap-1"):
                ui.link(video.display_name, f"/video/{video.video_id}").style(
                    "font-family: var(--ma-serif); font-size: 1.35rem; font-weight: 600; "
                    "text-decoration: none; color: inherit"
                )
                bits = [f"{video.n_runs} run" + ("" if video.n_runs == 1 else "s")]
                if video.methods:
                    bits.append(", ".join(video.methods))
                if video.resolutions:
                    order = settings.resolution_order
                    res_sorted = sorted(
                        video.resolutions,
                        key=lambda x: order.index(x) if x in order else 99,
                    )
                    bits.append(
                        f"{res_sorted[0]}–{res_sorted[-1]}"
                        if len(res_sorted) > 1
                        else res_sorted[0]
                    )
                if video.reference_label:
                    bits.append(video.reference_label)
                if video.last_import:
                    bits.append("imported " + video.last_import.strftime("%Y-%m-%d"))
                ui.label(" · ".join(bits)).classes("ma-meta")
                if video.notes:
                    snippet = video.notes.strip().splitlines()[0][:140]
                    ui.label(snippet).classes("ma-meta")
            with ui.column().classes("items-end gap-1 edit-chrome"):
                with ui.row().classes("gap-1"):
                    if video.n_warnings:
                        ui.label(f"{video.n_warnings} warn").classes("ma-chip warn")
                    if video.n_errors:
                        ui.label(f"{video.n_errors} err").classes("ma-chip danger")
                    if video.n_hidden:
                        ui.label(f"{video.n_hidden} hidden").classes("ma-chip quiet")
                with ui.row().classes("gap-0"):
                    ui.button(
                        icon="keyboard_arrow_up",
                        on_click=lambda v=video: _nudge(v.video_id, -1),
                    ).props("flat dense round")
                    ui.button(
                        icon="keyboard_arrow_down",
                        on_click=lambda v=video: _nudge(v.video_id, 1),
                    ).props("flat dense round")
                    if not video.is_unassigned:
                        ui.button(
                            icon="delete",
                            on_click=lambda v=video: _confirm_delete_video(v),
                        ).props("flat dense round color=negative")
        with ui.row().classes("gap-1 mt-2 flex-wrap"):
            for method in video.methods:
                ui.label(method).classes("ma-chip swatch").style(
                    f"--swatch: {method_color(method, settings)}"
                )
            for t in video.tags:
                ui.label(t).classes("ma-chip quiet")


def _confirm_delete_video(video) -> None:
    def do_delete() -> None:
        n = get_store().delete_video(video.video_id)
        ui.notify(
            f"Deleted {video.display_name} ({n} run"
            f"{'' if n == 1 else 's'}). Original CSVs were not touched."
        )
        ui.navigate.reload()

    confirm_dialog(
        f"Delete “{video.display_name}” from the library?",
        "This permanently removes the video and all of its runs from Metric Atelier. "
        "Original CSV files on disk are not modified.",
        on_confirm=do_delete,
    )


def _nudge(video_id: str, delta: int) -> None:
    store = get_store()
    videos = [v for v in store.list_video_summaries() if v.video_id != UNASSIGNED_VIDEO_ID]
    ids = [v.video_id for v in videos]
    if video_id not in ids:
        return
    index = ids.index(video_id)
    target = index + delta
    if target < 0 or target >= len(ids):
        return
    ids[index], ids[target] = ids[target], ids[index]
    store.reorder_videos(ids)
    ui.navigate.reload()
