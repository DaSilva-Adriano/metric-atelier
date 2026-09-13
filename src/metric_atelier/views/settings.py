"""Persisted display, import, chart, and data settings."""

from __future__ import annotations

import json

from nicegui import ui

from metric_atelier.metrics import CATALOG, DEFAULT_HERO_METRICS
from metric_atelier.models import CHART_ORDER_LABELS, CHART_TYPE_LABELS, AppSettings, IdentityRule
from metric_atelier.store import get_store, open_directory
from metric_atelier.theme import OKABE_ITO
from metric_atelier.views.common import app_frame


@ui.page("/settings")
def settings_page() -> None:
    with app_frame("settings"):
        store = get_store()
        settings = store.get_settings()
        ui.label("Settings").classes("ma-kicker")
        ui.label("Studio defaults").classes("ma-title")
        ui.label("These persist in the local SQLite annotation database.").classes("ma-lede")

        with ui.tabs().classes("mt-4") as tabs:
            ui.tab("Display")
            ui.tab("Import")
            ui.tab("Charts")
            ui.tab("Data")
        with ui.tab_panels(tabs, value="Display").classes("w-full"):
            with ui.tab_panel("Display"):
                _display_panel(store, settings)
            with ui.tab_panel("Import"):
                _import_panel(store, settings)
            with ui.tab_panel("Charts"):
                _charts_panel(store, settings)
            with ui.tab_panel("Data"):
                _data_panel(store, settings)


def _save(store, **changes) -> None:
    store.update_settings(**changes)
    ui.notify("Saved", type="positive")


def _display_panel(store, settings: AppSettings) -> None:
    ui.select(
        {"light": "Light paper", "dark": "Dark (print-safe)"}, value=settings.theme, label="Theme"
    ).classes("w-64").on_value_change(lambda e: _save(store, theme=e.value) or ui.navigate.reload())
    ui.input("Accent color", value=settings.accent_color).classes("w-48").on_value_change(
        lambda e: _save(store, accent_color=e.value or settings.accent_color)
    )
    ui.select(
        {90: "90%", 100: "100%", 115: "115%", 130: "130%"},
        value=settings.font_scale,
        label="Font scale",
    ).classes("w-48").on_value_change(
        lambda e: _save(store, font_scale=int(e.value)) or ui.navigate.reload()
    )
    ui.switch("Show raw filenames in tables", value=settings.show_raw_filenames).on_value_change(
        lambda e: _save(store, show_raw_filenames=bool(e.value))
    )
    ui.select({"en": "English"}, value=settings.language, label="Label language").classes("w-48")
    ui.separator()
    ui.label("Hero metrics").classes("text-sm uppercase tracking-wide")
    current = list(settings.hero_metrics)
    for key, spec in CATALOG.items():
        ui.checkbox(
            f"{spec.short_label} ({spec.better_hint})",
            value=key in current,
        ).on_value_change(lambda e, k=key: _toggle_hero(store, k, e.value))
    ui.separator()
    ui.label("Decimals").classes("text-sm uppercase tracking-wide")
    with ui.row().classes("gap-3 flex-wrap"):
        for key in DEFAULT_HERO_METRICS:
            spec = CATALOG[key]
            ui.number(
                spec.short_label,
                value=settings.decimal_places.get(key, spec.decimals),
                min=0,
                max=6,
                format="%.0f",
            ).classes("w-28").on_value_change(
                lambda e, k=key: _set_decimals(store, k, int(e.value or 0))
            )
    ui.separator()
    ui.label("Method display aliases").classes("text-sm uppercase tracking-wide")
    alias_box = (
        ui.textarea(
            value=_dict_to_lines(settings.method_display_aliases),
            placeholder="vsr = Video Super-Resolution",
        )
        .classes("w-full")
        .props("outlined autogrow")
    )
    ui.button(
        "Save aliases",
        on_click=lambda: _save(store, method_display_aliases=_lines_to_dict(alias_box.value or "")),
    ).props("outline")
    ui.label("Method colors (hex)").classes("text-sm uppercase tracking-wide mt-4")
    color_box = (
        ui.textarea(
            value=_dict_to_lines({**OKABE_ITO, **settings.method_colors}),
            placeholder="vsr = #009E73",
        )
        .classes("w-full")
        .props("outlined autogrow")
    )
    ui.button(
        "Save colors",
        on_click=lambda: _save(store, method_colors=_lines_to_dict(color_box.value or "")),
    ).props("outline")
    ui.input(
        "Resolution order (comma separated)",
        value=", ".join(settings.resolution_order),
    ).classes("w-full").on_value_change(
        lambda e: _save(
            store,
            resolution_order=[p.strip() for p in (e.value or "").split(",") if p.strip()],
        )
    )
    ui.input(
        "Method order (comma separated)",
        value=", ".join(settings.method_order),
    ).classes("w-full").on_value_change(
        lambda e: _save(
            store,
            method_order=[p.strip() for p in (e.value or "").split(",") if p.strip()],
        )
    )


def _toggle_hero(store, key: str, on: bool) -> None:
    settings = store.get_settings()
    hero = list(settings.hero_metrics)
    if on and key not in hero:
        hero.append(key)
    if not on and key in hero:
        hero.remove(key)
    _save(store, hero_metrics=hero)


def _set_decimals(store, key: str, places: int) -> None:
    settings = store.get_settings()
    decimals = dict(settings.decimal_places)
    decimals[key] = places
    _save(store, decimal_places=decimals)


def _import_panel(store, settings: AppSettings) -> None:
    ui.select(
        {"skip": "Skip duplicates", "refresh": "Refresh metrics only"},
        value=settings.reimport_mode,
        label="Default re-import behaviour",
    ).classes("w-80").on_value_change(lambda e: _save(store, reimport_mode=e.value))
    ui.textarea(
        "Extra method aliases (alias = canonical)",
        value=_dict_to_lines(settings.extra_method_aliases),
        placeholder="cubic = bicubic",
    ).classes("w-full").props("outlined autogrow").on_value_change(
        lambda e: _save(store, extra_method_aliases=_lines_to_dict(e.value or ""))
    )
    ui.textarea(
        "Extra parser regexes (one per line, named groups: title, method, res, fps)",
        value="\n".join(settings.extra_parser_regexes),
    ).classes("w-full").props("outlined autogrow").on_value_change(
        lambda e: _save(
            store,
            extra_parser_regexes=[ln.strip() for ln in (e.value or "").splitlines() if ln.strip()],
        )
    )
    ui.label("Identity rules — this name belongs to video X").classes(
        "text-sm uppercase tracking-wide"
    )
    rules_text = (
        ui.textarea(
            value=_rules_to_text(settings.identity_rules),
            placeholder="karting => kartingtime | Karting Time | regex=false",
        )
        .classes("w-full")
        .props("outlined autogrow")
    )
    ui.button(
        "Save identity rules",
        on_click=lambda: _save(store, identity_rules=_text_to_rules(rules_text.value or "")),
    ).props("outline")
    ui.label("Each line: pattern => video_id | optional display name | regex=true").classes(
        "ma-hint"
    )


def _charts_panel(store, settings: AppSettings) -> None:
    ui.select(
        CHART_TYPE_LABELS,
        value=settings.default_chart_type,
        label="Default chart",
    ).classes("w-64").on_value_change(lambda e: _save(store, default_chart_type=e.value))
    ui.select(
        CHART_ORDER_LABELS,
        value=settings.default_chart_order,
        label="Default chart order",
    ).classes("w-64").on_value_change(lambda e: _save(store, default_chart_order=e.value))
    ui.switch("Show values on bars", value=settings.show_bar_values).on_value_change(
        lambda e: _save(store, show_bar_values=bool(e.value))
    )
    ui.select(
        {"method": "Color by method", "resolution": "Color by resolution"},
        value=settings.color_by,
        label="Color encoding",
    ).classes("w-64").on_value_change(lambda e: _save(store, color_by=e.value))
    ui.select(
        {1: "1×", 2: "2×", 3: "3×"}, value=settings.export_scale, label="PNG export scale"
    ).classes("w-40").on_value_change(lambda e: _save(store, export_scale=int(e.value)))
    ui.select(
        {"white": "White background", "theme": "Theme background"},
        value=settings.export_background,
        label="Export background",
    ).classes("w-64").on_value_change(lambda e: _save(store, export_background=e.value))
    ui.number("Export width (px)", value=settings.export_width, min=1200, max=3600).classes(
        "w-48"
    ).on_value_change(lambda e: _save(store, export_width=int(e.value or 2000)))
    ui.label("Y-axis starts at zero").classes("text-sm uppercase tracking-wide")
    for key in DEFAULT_HERO_METRICS:
        spec = CATALOG[key]
        ui.switch(
            spec.short_label,
            value=settings.y_axis_zero.get(key, False),
        ).on_value_change(lambda e, k=key: _set_zero(store, k, bool(e.value)))
    ui.separator()
    ui.label("Metric thresholds").classes("text-sm uppercase tracking-wide")
    ui.label(
        "Drawn as a dotted reference line on charts. Table cells that miss the threshold "
        "are flagged. For ↑ metrics, values below the line fail; for ↓ metrics, values above fail. "
        "Leave empty to disable."
    ).classes("ma-hint")
    with ui.row().classes("gap-3 flex-wrap"):
        for key in DEFAULT_HERO_METRICS:
            spec = CATALOG[key]
            current = settings.metric_thresholds.get(key)
            ui.input(
                f"{spec.short_label} ({spec.arrow})",
                value="" if current is None else str(current),
            ).classes("w-36").props("dense outlined clearable").on_value_change(
                lambda e, k=key: _set_threshold(store, k, e.value)
            )


def _set_zero(store, key: str, on: bool) -> None:
    settings = store.get_settings()
    zeros = dict(settings.y_axis_zero)
    zeros[key] = on
    _save(store, y_axis_zero=zeros)


def _set_threshold(store, key: str, value) -> None:
    settings = store.get_settings()
    thresholds = dict(settings.metric_thresholds)
    if value is None or value == "":
        thresholds.pop(key, None)
    else:
        try:
            thresholds[key] = float(value)
        except (TypeError, ValueError):
            return
    _save(store, metric_thresholds=thresholds)


def _data_panel(store, settings: AppSettings) -> None:
    ui.switch("Reveal hidden runs by default", value=settings.reveal_hidden).on_value_change(
        lambda e: _save(store, reveal_hidden=bool(e.value))
    )
    ui.button("Open data directory", on_click=lambda: open_directory(store.data_dir)).props(
        "unelevated"
    )
    ui.label(str(store.data_dir)).classes("ma-meta")

    ui.separator()
    ui.label("Imported files").classes("text-sm uppercase tracking-wide")
    files = store.list_imported_files()
    if not files:
        ui.label("Nothing imported yet.").classes("ma-hint")
    for item in files:
        with ui.row().classes("w-full items-center justify-between"):
            ui.label(f"{item.basename} · {item.n_rows} rows · {item.imported_at:%Y-%m-%d}").classes(
                "ma-meta"
            )
            ui.button(
                "Delete runs",
                on_click=lambda h=item.file_hash: _delete_file(store, h),
            ).props("flat dense color=negative")

    ui.separator()
    ui.label("Soft-deleted runs").classes("text-sm uppercase tracking-wide")
    deleted = [
        r for r in store.list_runs(include_hidden=True, include_deleted=True) if r.deleted_at
    ]
    if not deleted:
        ui.label("None.").classes("ma-hint")
    for run in deleted[:50]:
        with ui.row().classes("w-full items-center justify-between"):
            ui.label(run.raw_name).classes("ma-meta")
            ui.button(
                "Undo",
                on_click=lambda rid=run.run_id: store.restore_runs([rid]) or ui.navigate.reload(),
            ).props("flat dense")

    ui.separator()
    ui.label("Annotation database").classes("text-sm uppercase tracking-wide")

    def do_export() -> None:
        payload = store.export_annotations()
        path = store.data_dir / "exports" / "annotations.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        ui.download.file(str(path))

    ui.button("Export annotations JSON", on_click=do_export).props("outline")

    def do_dataset_export() -> None:
        payload = store.export_dataset()
        path = store.data_dir / "exports" / "dataset.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        ui.download.file(str(path))

    ui.button("Export dataset JSON", on_click=do_dataset_export).props("unelevated")
    ui.label(
        "Dataset JSON stores method, resolution, fps, and metric values as fields. "
        "Names are labels only — consumers should not parse vsr/bicubic/1080p out of filenames."
    ).classes("ma-hint")

    async def on_ann(e) -> None:
        text = e.file.text()
        if hasattr(text, "__await__"):
            text = await text
        payload = json.loads(text)
        store.import_annotations(payload)
        ui.notify("Annotations imported.", type="positive")

    ui.upload(on_upload=on_ann, auto_upload=True, label="Import annotations JSON").props(
        "accept=.json"
    )


def _delete_file(store, file_hash: str) -> None:
    n = store.delete_imported_file(file_hash)
    ui.notify(f"Removed {n} runs from the database. Original CSVs were not touched.")
    ui.navigate.reload()


def _dict_to_lines(mapping: dict[str, str]) -> str:
    return "\n".join(f"{k} = {v}" for k, v in mapping.items())


def _lines_to_dict(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if key:
            out[key] = value
    return out


def _rules_to_text(rules: list[IdentityRule]) -> str:
    lines = []
    for rule in rules:
        flag = "regex=true" if rule.is_regex else "regex=false"
        display = rule.display_name or ""
        lines.append(f"{rule.pattern} => {rule.video_id} | {display} | {flag}")
    return "\n".join(lines)


def _text_to_rules(text: str) -> list[IdentityRule]:
    rules: list[IdentityRule] = []
    for line in text.splitlines():
        if "=>" not in line:
            continue
        left, right = line.split("=>", 1)
        parts = [p.strip() for p in right.split("|")]
        video_id = parts[0] if parts else ""
        display = parts[1] if len(parts) > 1 and parts[1] else None
        is_regex = len(parts) > 2 and "true" in parts[2].lower()
        if video_id:
            rules.append(
                IdentityRule(
                    pattern=left.strip(), video_id=video_id, display_name=display, is_regex=is_regex
                )
            )
    return rules
