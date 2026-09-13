"""Paper theme, colorblind-safe palettes, and global CSS."""

from __future__ import annotations

from dataclasses import dataclass

from metric_atelier.models import AppSettings

OKABE_ITO = {
    "bicubic": "#E69F00",
    "lanczos": "#56B4E9",
    "vsr": "#009E73",
    "bilinear": "#CC79A7",
    "nearest": "#D55E00",
    "esrgan": "#0072B2",
    "realesrgan": "#0072B2",
    "swinir": "#F0E442",
    "basicvsr": "#009E73",
    "ia": "#CC79A7",
    "native": "#7A746C",
    "unknown": "#9A9186",
}

RESOLUTION_COLORS = {
    "360p": "#C4B7A6",
    "480p": "#A89070",
    "720p": "#7A9B84",
    "1080p": "#3D5C4A",
    "1440p": "#3A5A78",
    "2160p": "#1F2F3A",
    "unknown": "#9A9186",
}

RESOLUTION_SYMBOLS = {
    "360p": "circle",
    "480p": "square",
    "720p": "diamond",
    "1080p": "triangle-up",
    "1440p": "triangle-down",
    "2160p": "x",
    "unknown": "circle-open",
}

FONTS_HTML = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600;8..60,700&display=swap" rel="stylesheet">
"""

THEME_CSS = r"""
:root {
  --ma-bg: #f3eee4;
  --ma-paper: #fbf7f0;
  --ma-elev: #fffdf8;
  --ma-ink: #2a2622;
  --ma-muted: #6f675d;
  --ma-faint: #9a9186;
  --ma-line: #e4d9c8;
  --ma-line-strong: #cfc1ab;
  --ma-accent: #3d5c4a;
  --ma-accent-soft: #e4efe8;
  --ma-warn: #9a6b24;
  --ma-warn-bg: #f4e6cc;
  --ma-danger: #8b3d32;
  --ma-danger-bg: #f3ddd8;
  --ma-ok: #3d5c4a;
  --ma-shadow: 0 1px 2px rgba(42,38,34,0.04), 0 10px 28px rgba(42,38,34,0.06);
  --ma-serif: "Source Serif 4", "Iowan Old Style", Georgia, serif;
  --ma-sans: Inter, "Segoe UI", system-ui, sans-serif;
  --ma-scale: 1;
}
.ma-shell.ma-dark {
  --ma-bg: #1b1916;
  --ma-paper: #23201c;
  --ma-elev: #2c2823;
  --ma-ink: #ece5d8;
  --ma-muted: #b5aa9c;
  --ma-faint: #8c8276;
  --ma-line: #3a342c;
  --ma-line-strong: #4e463c;
  --ma-accent: #8fbf9a;
  --ma-accent-soft: #2a3a30;
  --ma-warn: #d4a04a;
  --ma-warn-bg: #3a2e1a;
  --ma-danger: #d9897c;
  --ma-danger-bg: #3a2420;
  --ma-ok: #8fbf9a;
  --ma-shadow: 0 1px 2px rgba(0,0,0,0.2), 0 12px 32px rgba(0,0,0,0.28);
}
html, body, #app {
  background: var(--ma-bg) !important;
  color: var(--ma-ink);
  font-family: var(--ma-sans);
}
.q-drawer, .q-header, .q-page, .q-layout {
  background: transparent !important;
}
.ma-shell {
  background: var(--ma-bg);
  color: var(--ma-ink);
  min-height: 100vh;
  width: 100%;
  font-family: var(--ma-sans);
  font-size: calc(16px * var(--ma-scale, 1));
  letter-spacing: 0.01em;
}
.ma-rail {
  width: 13.5rem;
  min-width: 13.5rem;
  padding: 24px 16px;
  border-right: 1px solid var(--ma-line);
  background: var(--ma-paper);
  gap: 4px !important;
}
.ma-brand {
  font-family: var(--ma-serif);
  font-size: 1.35rem;
  font-weight: 600;
  line-height: 1.2;
  color: var(--ma-ink);
  margin: 0 0 4px;
}
.ma-brand-sub {
  color: var(--ma-muted);
  font-size: 0.75rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  margin-bottom: 24px;
}
.ma-nav {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 8px;
  color: var(--ma-muted);
  text-decoration: none;
  font-weight: 500;
}
.ma-nav:hover { background: var(--ma-accent-soft); color: var(--ma-ink); }
.ma-nav.active {
  background: var(--ma-accent-soft);
  color: var(--ma-accent);
}
.ma-main {
  flex: 1;
  min-width: 0;
  padding: 24px 32px 48px;
  max-width: 1600px;
}
.ma-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 24px;
}
.ma-kicker {
  font-size: 0.75rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--ma-faint);
  margin-bottom: 4px;
}
.ma-title {
  font-family: var(--ma-serif);
  font-size: 2rem;
  font-weight: 600;
  line-height: 1.2;
  margin: 0;
}
.ma-lede {
  color: var(--ma-muted);
  max-width: 42rem;
  line-height: 1.55;
}
.ma-card {
  background: var(--ma-elev);
  border: 1px solid var(--ma-line);
  border-radius: 12px;
  box-shadow: var(--ma-shadow);
  padding: 20px 22px;
}
.ma-card.clickable { cursor: pointer; }
.ma-card.clickable:hover { border-color: var(--ma-line-strong); }
.ma-card.highlight {
  outline: 2px solid var(--ma-accent);
  outline-offset: 2px;
}
.ma-meta {
  color: var(--ma-muted);
  font-size: 0.9rem;
  line-height: 1.45;
}
.ma-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.02em;
  background: var(--ma-accent-soft);
  color: var(--ma-accent);
  border: 1px solid transparent;
}
.ma-chip.warn { background: var(--ma-warn-bg); color: var(--ma-warn); }
.ma-chip.danger { background: var(--ma-danger-bg); color: var(--ma-danger); }
.ma-chip.quiet { background: transparent; color: var(--ma-muted); border-color: var(--ma-line); }
.ma-chip.swatch::before {
  content: "";
  width: 8px; height: 8px; border-radius: 99px;
  background: var(--swatch, var(--ma-accent));
}
.ma-empty {
  padding: 64px 24px;
  text-align: center;
  border: 1px dashed var(--ma-line-strong);
  border-radius: 16px;
  background: var(--ma-paper);
}
.ma-empty h2 {
  font-family: var(--ma-serif);
  font-size: 1.6rem;
  margin: 0 0 8px;
}
.ma-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin: 8px 0 16px;
}
.q-btn {
  text-transform: none !important;
  letter-spacing: 0.01em;
  font-weight: 500 !important;
  border-radius: 8px !important;
}
.q-field__control, .q-field__native, .q-field__input {
  color: var(--ma-ink) !important;
}
.q-table, .q-table th, .q-table td {
  background: var(--ma-elev) !important;
  color: var(--ma-ink) !important;
  border-color: var(--ma-line) !important;
  font-variant-numeric: tabular-nums lining-nums;
}
.q-table thead th {
  font-size: 0.72rem !important;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--ma-muted) !important;
  font-weight: 600 !important;
}
.q-table tbody td {
  font-size: 0.92rem;
}
.q-table tbody tr.ma-new {
  background: var(--ma-accent-soft) !important;
}
.q-table--dense td, .q-table--dense th { padding: 6px 10px !important; }
.ma-num { font-variant-numeric: tabular-nums lining-nums; text-align: right; }
.ma-fail { color: var(--ma-danger) !important; font-weight: 600; }
.ma-chip.fail { background: var(--ma-danger-bg); color: var(--ma-danger); }
.ma-drop {
  border: 1.5px dashed var(--ma-line-strong);
  border-radius: 12px;
  background: var(--ma-paper);
  padding: 18px;
  text-align: center;
  color: var(--ma-muted);
}
.q-uploader { width: 100%; }
.q-uploader__header { display: none !important; }
.ma-hint { color: var(--ma-faint); font-size: 0.8rem; }
.ma-present .edit-chrome { display: none !important; }
.ma-present .ma-title { font-size: 2.35rem; }
.ma-present .q-table tbody td { font-size: 1rem; }
.ma-drawer-panel { width: min(420px, 92vw); }
.js-plotly-plot .plotly .main-svg { font-family: var(--ma-sans) !important; }
.q-card { background: var(--ma-elev) !important; color: var(--ma-ink) !important; }
.q-dialog__inner .q-card { box-shadow: var(--ma-shadow); border: 1px solid var(--ma-line); }
.q-separator { background: var(--ma-line) !important; }
.q-tab { text-transform: none !important; }
.q-checkbox__label, .q-toggle__label { color: var(--ma-ink); }
.q-item { color: var(--ma-ink); }
a { color: var(--ma-accent); }
.ma-note-preview p { margin: 0.4em 0; }
.ma-grip { cursor: grab; color: var(--ma-faint); }
"""


@dataclass(frozen=True)
class ThemeColors:
    bg: str
    paper: str
    ink: str
    muted: str
    line: str
    grid: str
    accent: str


def theme_colors(settings: AppSettings) -> ThemeColors:
    if settings.theme == "dark":
        return ThemeColors(
            bg="#1b1916",
            paper="#23201c",
            ink="#ece5d8",
            muted="#b5aa9c",
            line="#3a342c",
            grid="#3a342c",
            accent=settings.accent_color or "#8fbf9a",
        )
    return ThemeColors(
        bg="#f3eee4",
        paper="#fffdf8" if settings.export_background == "white" else "#fbf7f0",
        ink="#2a2622",
        muted="#6f675d",
        line="#e4d9c8",
        grid="#efe6d8",
        accent=settings.accent_color or "#3d5c4a",
    )


def method_color(method: str | None, settings: AppSettings) -> str:
    key = (method or "unknown").lower()
    if key in settings.method_colors:
        return settings.method_colors[key]
    return OKABE_ITO.get(key, OKABE_ITO["unknown"])


def resolution_color(label: str) -> str:
    return RESOLUTION_COLORS.get(label, RESOLUTION_COLORS["unknown"])


def apply_theme(settings: AppSettings) -> None:
    from nicegui import ui

    ui.add_head_html(FONTS_HTML)
    ui.add_css(THEME_CSS)
    ui.colors(
        primary=settings.accent_color,
        secondary="#9A6B2F",
        accent=settings.accent_color,
        dark="#1b1916",
        positive="#3D5C4A",
        negative="#8B3D32",
        info="#3A5A78",
        warning="#9A6B24",
    )
    scale = settings.font_scale / 100
    if settings.presentation_mode:
        scale = max(scale, 1.15)
    ui.query("body").classes("ma-body")
    ui.add_css(f".ma-shell {{ --ma-scale: {scale}; --ma-accent: {settings.accent_color}; }}")
    dark = ui.dark_mode()
    if settings.theme == "dark":
        dark.enable()
    else:
        dark.disable()
