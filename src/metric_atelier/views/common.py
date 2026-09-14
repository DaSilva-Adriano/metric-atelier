"""Shared chrome, import dialog, formatting helpers, and keyboard shortcuts."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from contextlib import contextmanager
from pathlib import Path

from nicegui import app, ui

from metric_atelier.ingest import CsvSource, collect_csv_paths
from metric_atelier.metrics import ALL_METRICS_KEY, format_metric, metric_choice_options
from metric_atelier.models import AppSettings, RunDTO
from metric_atelier.store import get_store
from metric_atelier.theme import apply_theme, method_color


def find_samples_dir() -> Path | None:
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "samples"
        if candidate.is_dir() and (candidate / "beauty.csv").exists():
            return candidate
    cwd = Path.cwd() / "samples"
    if cwd.is_dir() and (cwd / "beauty.csv").exists():
        return cwd
    return None


def format_fps(value: float | None) -> str:
    if value is None:
        return "—"
    if float(value).is_integer():
        return str(int(value))
    return f"{value:g}"


def metric_cell(run: RunDTO, key: str, settings: AppSettings) -> str:
    return format_metric(key, run.metric(key), decimals=settings.decimal_places)


def metric_filter_chips(
    hero_metrics: Sequence[str],
    state: dict[str, str],
    on_change: Callable[[], None],
) -> None:
    """Exclusive All / VMAF / PSNR / … chips. ``state['value']`` holds the choice."""
    options = metric_choice_options(hero_metrics)
    current = state.get("value") or ALL_METRICS_KEY
    if current not in options:
        current = ALL_METRICS_KEY
        state["value"] = current
    ui.label("Metric").classes("ma-hint self-center")
    for key, label in options.items():
        ui.chip(
            label,
            selectable=True,
            selected=key == current,
            color=None,
            on_selection_change=lambda e, k=key: _toggle_metric_chip(e, k, state, on_change),
        ).props("outline dense")


def _toggle_metric_chip(e, key: str, state: dict[str, str], on_change: Callable[[], None]) -> None:
    if e.value:
        if state.get("value") == key:
            return
        state["value"] = key
        on_change()
        return
    if state.get("value") == key:
        on_change()


def nav_class(active: str, name: str) -> str:
    return "ma-nav active" if active == name else "ma-nav"


@contextmanager
def app_frame(active: str):
    store = get_store()
    settings = store.get_settings()
    apply_theme(settings)
    shell_cls = "ma-shell w-full no-wrap items-stretch"
    if settings.theme == "dark":
        shell_cls += " ma-dark"
    if settings.presentation_mode:
        shell_cls += " ma-present"
    with ui.row().classes(shell_cls):
        with ui.column().classes("ma-rail edit-chrome"):
            ui.label("Metric Atelier").classes("ma-brand")
            ui.label("Quality figures").classes("ma-brand-sub")
            ui.link("Library", "/").classes(nav_class(active, "library"))
            ui.link("Compare", "/compare").classes(nav_class(active, "compare"))
            ui.link("Settings", "/settings").classes(nav_class(active, "settings"))
            ui.space()
            ui.button(
                "Presentation" if not settings.presentation_mode else "Editing",
                icon="crop_original",
                on_click=lambda: _toggle_presentation(),
            ).props("flat dense").classes("w-full")
        with ui.column().classes("ma-main"):
            yield settings
    _install_shortcuts()


def _toggle_presentation() -> None:
    store = get_store()
    settings = store.get_settings()
    store.update_settings(presentation_mode=not settings.presentation_mode)
    ui.navigate.reload()


def _install_shortcuts() -> None:
    dialog = ui.dialog()
    with dialog, ui.card().classes("w-[32rem]"):
        ui.label("Keyboard").classes("text-lg font-medium")
        ui.markdown(
            "- `/` focus search\n"
            "- `i` import CSVs\n"
            "- `h` hide selected runs\n"
            "- `p` presentation mode\n"
            "- `?` this list\n"
            "- `1` library · `2` compare · `3` settings"
        )
        ui.button("Close", on_click=dialog.close).props("flat")

    def on_key(e) -> None:
        if not e.action.keydown or e.action.repeat:
            return
        key = str(e.key)
        if key == "?" or (e.modifiers.shift and key == "/"):
            dialog.open()
        elif key == "p" and not e.modifiers.ctrl:
            _toggle_presentation()
        elif key == "1":
            ui.navigate.to("/")
        elif key == "2":
            ui.navigate.to("/compare")
        elif key == "3":
            ui.navigate.to("/settings")
        elif key == "/":
            ui.run_javascript(
                "document.querySelector('.ma-search input, .ma-search textarea')?.focus()"
            )
        elif key == "i":
            open_import_dialog()

    ui.keyboard(on_key=on_key, repeating=False)


async def _read_upload(event) -> tuple[str, bytes]:
    upload = event.file
    name = upload.name
    payload = upload.read()
    if hasattr(payload, "__await__"):
        payload = await payload
    return name, payload


def open_import_dialog(
    *,
    force_video_id: str | None = None,
    initial: list[CsvSource] | None = None,
    on_done: Callable[[], None] | None = None,
) -> None:
    store = get_store()
    staged: list[CsvSource] = list(initial or [])
    force = {"id": force_video_id}
    mode = {"value": store.get_settings().reimport_mode}

    dialog = ui.dialog().props("maximized=false")
    with dialog, ui.card().classes("w-[56rem] max-w-[94vw]"):
        ui.label("Import summary CSV").classes("text-xl").style(
            "font-family: var(--ma-serif); font-weight: 600"
        )
        ui.label(
            "Original files are only read. A snapshot is stored under the data directory."
        ).classes("ma-lede")

        preview_host = ui.column().classes("w-full gap-3")
        path_in = (
            ui.input("Or a local folder / file path").classes("w-full").props("dense outlined")
        )

        def render_preview() -> None:
            preview_host.clear()
            with preview_host:
                if not staged:
                    ui.label("Drop CSV files, pick them below, or paste a path.").classes("ma-hint")
                    return
                preview = store.preview_sources(
                    staged, force_video_id=force["id"], reimport_mode=mode["value"]
                )
                with ui.row().classes("gap-4 flex-wrap"):
                    _stat("New", preview.n_new)
                    _stat("Duplicates", preview.n_duplicate)
                    _stat("Refresh", preview.n_refresh)
                    _stat("Assigned", preview.n_assigned)
                    _stat("Unassigned", preview.n_unassigned)
                    _stat("With errors", preview.n_errors)
                ui.table(
                    columns=[
                        {
                            "name": "raw_name",
                            "label": "Distorted",
                            "field": "raw_name",
                            "align": "left",
                        },
                        {"name": "video_display", "label": "Video", "field": "video_display"},
                        {"name": "method", "label": "Method", "field": "method"},
                        {"name": "resolution_label", "label": "Res", "field": "resolution_label"},
                        {"name": "status", "label": "Status", "field": "status"},
                    ],
                    rows=[r.model_dump() for r in preview.rows[:80]],
                    row_key="run_id",
                    pagination=20,
                ).classes("w-full").props("dense flat")
                if len(preview.rows) > 80:
                    ui.label(f"Showing 80 of {len(preview.rows)} rows.").classes("ma-hint")

        async def on_upload(event) -> None:
            name, data = await _read_upload(event)
            staged.append(CsvSource(name=name, content=data, original_path=None))
            render_preview()

        ui.upload(
            on_upload=on_upload,
            multiple=True,
            auto_upload=True,
            label="Drop CSV files here",
        ).props("accept=.csv").classes("w-full ma-drop")

        def load_path() -> None:
            raw = (path_in.value or "").strip().strip('"')
            if not raw:
                return
            paths = collect_csv_paths(Path(raw))
            if not paths:
                ui.notify("No CSV files found at that path.", type="warning")
                return
            for path in paths:
                staged.append(
                    CsvSource(
                        name=path.name, content=path.read_bytes(), original_path=str(path.resolve())
                    )
                )
            render_preview()

        with ui.row().classes("items-end w-full gap-2"):
            path_in.classes("flex-grow")
            ui.button("Read path", on_click=load_path).props("outline")

        videos = store.list_videos()
        options = {v.video_id: v.display_name for v in videos}
        options["__auto__"] = "Auto-assign from filename"
        assign = ui.select(
            options,
            value=force_video_id or "__auto__",
            label="Assign to",
        ).classes("w-64")

        def on_assign(e) -> None:
            force["id"] = None if e.value == "__auto__" else e.value
            render_preview()

        assign.on_value_change(on_assign)

        ui.select(
            {"skip": "Skip duplicates", "refresh": "Refresh metrics (keep notes/names/hidden)"},
            value=mode["value"],
            label="Re-import",
        ).on_value_change(lambda e: mode.update(value=e.value) or render_preview()).classes("w-96")

        def confirm() -> None:
            if not staged:
                ui.notify("Nothing to import.", type="warning")
                return
            result = store.commit_sources(
                staged, force_video_id=force["id"], reimport_mode=mode["value"]
            )
            app.storage.user["highlight_runs"] = result.new_run_ids
            app.storage.user["highlight_videos"] = result.affected_video_ids
            dialog.close()
            ui.notify(
                f"Imported {result.n_new} new · {result.n_duplicate} skipped · "
                f"{result.n_refresh} refreshed · {result.n_unassigned} unassigned",
                type="positive",
            )
            if on_done:
                on_done()
            elif len(result.affected_video_ids) == 1:
                ui.navigate.to(f"/video/{result.affected_video_ids[0]}")
            else:
                ui.navigate.to("/")

        with ui.row().classes("w-full justify-end gap-2 mt-2"):
            ui.button("Cancel", on_click=dialog.close).props("flat")
            ui.button("Import", on_click=confirm).props("unelevated")

        render_preview()
    dialog.open()


def _stat(label: str, value: int) -> None:
    with ui.column().classes("items-start"):
        ui.label(str(value)).classes("text-2xl").style(
            "font-variant-numeric: tabular-nums; font-weight: 600"
        )
        ui.label(label).classes("ma-hint")


def load_samples_into_store() -> int:
    samples = find_samples_dir()
    if samples is None:
        raise FileNotFoundError("samples/ folder with beauty.csv was not found.")
    result = get_store().import_paths([samples / "beauty.csv", samples / "kartingtime.csv"])
    app.storage.user["highlight_runs"] = result.new_run_ids
    app.storage.user["highlight_videos"] = result.affected_video_ids
    return result.n_new


def status_chips(run: RunDTO) -> str:
    bits: list[str] = []
    if run.errors:
        bits.append("error")
    if run.warnings:
        bits.append("warn")
    if run.hidden:
        bits.append("hidden")
    return ", ".join(bits) if bits else ""


def method_chip_style(method: str | None, settings: AppSettings) -> str:
    return f"--swatch: {method_color(method, settings)}"


def confirm_dialog(
    title: str,
    body: str,
    *,
    confirm_label: str = "Delete",
    on_confirm: Callable[[], None],
) -> None:
    dialog = ui.dialog()
    with dialog, ui.card().classes("w-[30rem] max-w-[94vw]"):
        ui.label(title).style("font-family: var(--ma-serif); font-size: 1.2rem; font-weight: 600")
        ui.label(body).classes("ma-lede")
        with ui.row().classes("w-full justify-end gap-2 mt-3"):
            ui.button("Cancel", on_click=dialog.close).props("flat")

            def accept() -> None:
                dialog.close()
                on_confirm()

            ui.button(confirm_label, on_click=accept).props("unelevated color=negative")
    dialog.open()
