"""Publication-ready Plotly charts with a muted paper theme."""

from __future__ import annotations

from collections.abc import Sequence

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from metric_atelier.grouping import friendly_run_name, method_short_label, reference_label
from metric_atelier.metrics import CATALOG, direction_caption, format_metric
from metric_atelier.models import AppSettings, RunDTO, SourceVideo
from metric_atelier.theme import RESOLUTION_SYMBOLS, method_color, resolution_color, theme_colors


def visible_runs(
    runs: Sequence[RunDTO],
    *,
    include_hidden: bool,
    hidden_methods: set[str] | None = None,
    hidden_resolutions: set[str] | None = None,
) -> list[RunDTO]:
    hidden_methods = hidden_methods or set()
    hidden_resolutions = hidden_resolutions or set()
    out: list[RunDTO] = []
    for run in runs:
        if run.deleted_at is not None:
            continue
        if run.hidden and not include_hidden:
            continue
        if run.method and run.method in hidden_methods:
            continue
        if run.resolution_label in hidden_resolutions:
            continue
        out.append(run)
    return out


def auto_subtitle(
    runs: Sequence[RunDTO],
    video: SourceVideo | None = None,
    settings: AppSettings | None = None,
) -> str:
    methods = sorted({r.method for r in runs if r.method})
    present = {r.resolution_label for r in runs if r.resolution_label != "unknown"}
    order = list(settings.resolution_order) if settings is not None else [
        "360p",
        "480p",
        "720p",
        "1080p",
        "1440p",
        "2160p",
    ]
    resolutions = [label for label in order if label in present]
    resolutions += sorted(present - set(resolutions))
    bits = []
    if video is not None:
        ref = reference_label(video)
        if ref:
            bits.append(ref)
    if resolutions:
        bits.append("–".join(resolutions) if len(resolutions) > 1 else resolutions[0])
    if methods:
        bits.append(", ".join(methods))
    bits.append(f"{len(runs)} run" + ("" if len(runs) == 1 else "s"))
    return " · ".join(bits)


def publication_layout(
    *,
    title: str,
    subtitle: str,
    settings: AppSettings,
    height: int,
    caption: str = "",
    legend: bool = True,
    caption_yshift: int = -108,
) -> dict:
    colors = theme_colors(settings)
    paper = (
        "#ffffff"
        if settings.export_background == "white" and settings.theme == "light"
        else colors.paper
    )
    full_title = title
    if subtitle:
        full_title = (
            f"{title}<br>"
            f"<span style='font-size:13px;line-height:1.7;color:{colors.muted};font-weight:400'>"
            f"{subtitle}</span>"
        )
    annotations = []
    if caption:
        # Paper y=0 is the bottom of the plot domain. Tick labels hang below that,
        # so shift the footer further down into the margin instead of mixing with axes.
        annotations.append(
            dict(
                text=caption,
                xref="paper",
                yref="paper",
                x=0,
                y=0,
                xanchor="left",
                yanchor="top",
                xshift=0,
                yshift=caption_yshift,
                showarrow=False,
                align="left",
                font=dict(size=12, color=colors.muted, family="Inter, Segoe UI, sans-serif"),
            )
        )
    return dict(
        title=dict(
            text=full_title,
            font=dict(size=18, family="Source Serif 4, Georgia, serif", color=colors.ink),
            x=0,
            xref="container",
            xanchor="left",
            y=1,
            yref="container",
            yanchor="top",
            pad=dict(t=48, b=28, l=48, r=48),
        ),
        font=dict(family="Inter, Segoe UI, sans-serif", size=13, color=colors.ink),
        paper_bgcolor=paper,
        plot_bgcolor=paper,
        margin=dict(l=96, r=64, t=160, b=188 if caption else 80, pad=8),
        height=height,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            x=0,
            xanchor="left",
            bgcolor="rgba(0,0,0,0)",
            font=dict(size=12),
        )
        if legend
        else dict(tracegroupgap=0),
        showlegend=legend,
        hoverlabel=dict(font=dict(size=12, family="Inter, Segoe UI, sans-serif")),
        annotations=annotations,
        bargap=0.28,
        bargroupgap=0.08,
        separators=".,",
    )


def _yaxis(key: str, settings: AppSettings) -> dict:
    colors = theme_colors(settings)
    spec = CATALOG.get(key)
    title = spec.short_label if spec else key
    hint = spec.better_hint if spec else ""
    zero = settings.y_axis_zero.get(key, False)
    return dict(
        title=dict(text=f"{title} ({hint})" if hint else title, font=dict(size=13)),
        tickfont=dict(size=12),
        gridcolor=colors.grid,
        gridwidth=1,
        zeroline=False,
        showline=True,
        linecolor=colors.line,
        rangemode="tozero" if zero else "normal",
        separatethousands=False,
    )


def _xaxis(title: str, settings: AppSettings) -> dict:
    colors = theme_colors(settings)
    return dict(
        title=dict(text=title, font=dict(size=13)),
        tickfont=dict(size=12),
        showgrid=False,
        showline=True,
        linecolor=colors.line,
        ticks="outside",
    )


def _ordered_resolutions(runs: Sequence[RunDTO], settings: AppSettings) -> list[str]:
    present = {run.resolution_label for run in runs}
    ordered = [label for label in settings.resolution_order if label in present]
    extra = sorted(present - set(ordered))
    return ordered + extra


def _ordered_methods(runs: Sequence[RunDTO]) -> list[str]:
    preferred = [
        "bicubic",
        "bilinear",
        "lanczos",
        "nearest",
        "vsr",
        "esrgan",
        "realesrgan",
        "swinir",
        "native",
    ]
    present = [m for m in preferred if any(r.method == m for r in runs)]
    rest = sorted({r.method or "unknown" for r in runs} - set(present))
    return present + rest


def _color_for(run: RunDTO, settings: AppSettings) -> str:
    if run.color:
        return run.color
    if settings.color_by == "resolution":
        return resolution_color(run.resolution_label)
    return method_color(run.method, settings)


def build_small_multiples(
    runs: Sequence[RunDTO],
    metrics: Sequence[str],
    settings: AppSettings,
    *,
    title: str,
    subtitle: str,
    video_labels: dict[str, str] | None = None,
) -> go.Figure:
    keys = [k for k in metrics if k in CATALOG] or list(metrics)
    n = len(keys)
    cols = 3 if n > 2 else n
    rows_n = (n + cols - 1) // cols
    fig = make_subplots(
        rows=rows_n,
        cols=cols,
        subplot_titles=[
            f"{CATALOG[k].short_label} {CATALOG[k].arrow}" if k in CATALOG else k for k in keys
        ],
        vertical_spacing=0.14,
        horizontal_spacing=0.08,
    )
    methods = _ordered_methods(runs)
    resolutions = _ordered_resolutions(runs, settings)
    show_text = settings.show_bar_values and len(methods) * len(resolutions) <= 8
    for index, key in enumerate(keys):
        row = index // cols + 1
        col = index % cols + 1
        spec = CATALOG.get(key)
        for method in methods:
            xs: list[str] = []
            ys: list[float | None] = []
            texts: list[str] = []
            for res in resolutions:
                match = [
                    r
                    for r in runs
                    if (r.method or "unknown") == method and r.resolution_label == res
                ]
                value = match[0].metric(key) if match else None
                xs.append(res)
                ys.append(value)
                texts.append(format_metric(key, value) if value is not None else "")
            color = method_color(method, settings)
            fig.add_trace(
                go.Bar(
                    name=method_short_label(method, settings),
                    x=xs,
                    y=ys,
                    marker=dict(color=color, line=dict(width=0)),
                    text=texts if show_text else None,
                    textposition="outside",
                    textfont=dict(size=11),
                    legendgroup=method,
                    showlegend=(index == 0),
                    hovertemplate="%{x}<br>%{y}<extra>"
                    + method_short_label(method, settings)
                    + "</extra>",
                ),
                row=row,
                col=col,
            )
        fig.update_xaxes(_xaxis("", settings), row=row, col=col)
        fig.update_yaxes(_yaxis(key, settings), row=row, col=col)
        if spec and not settings.y_axis_zero.get(key, False) and spec.typical_max <= 1:
            fig.update_yaxes(range=[None, None], row=row, col=col)
    layout = publication_layout(
        title=title,
        subtitle=subtitle,
        settings=settings,
        height=280 * rows_n + 160,
        caption=direction_caption(keys),
    )
    layout["legend"] = dict(
        orientation="h",
        yanchor="bottom",
        y=1.02,
        x=0,
        xanchor="left",
        bgcolor="rgba(0,0,0,0)",
        font=dict(size=12),
    )
    fig.update_layout(**layout, barmode="group")
    return fig


def build_grouped_bar(
    runs: Sequence[RunDTO],
    metric: str,
    settings: AppSettings,
    *,
    title: str,
    subtitle: str,
    group_by: str = "resolution",
) -> go.Figure:
    fig = go.Figure()
    methods = _ordered_methods(runs)
    resolutions = _ordered_resolutions(runs, settings)
    show_text = settings.show_bar_values and len(runs) <= 16
    if group_by == "method":
        categories = [method_short_label(m, settings) for m in methods]
        series = resolutions
        for res in series:
            xs, ys, texts = [], [], []
            for method in methods:
                match = [
                    r
                    for r in runs
                    if (r.method or "unknown") == method and r.resolution_label == res
                ]
                value = match[0].metric(metric) if match else None
                xs.append(method_short_label(method, settings))
                ys.append(value)
                texts.append(format_metric(metric, value) if value is not None else "")
            fig.add_trace(
                go.Bar(
                    name=res,
                    x=xs,
                    y=ys,
                    marker=dict(color=resolution_color(res)),
                    text=texts if show_text else None,
                    textposition="outside",
                )
            )
        x_title = "Method"
    else:
        categories = resolutions
        for method in methods:
            xs, ys, texts = [], [], []
            for res in resolutions:
                match = [
                    r
                    for r in runs
                    if (r.method or "unknown") == method and r.resolution_label == res
                ]
                value = match[0].metric(metric) if match else None
                xs.append(res)
                ys.append(value)
                texts.append(format_metric(metric, value) if value is not None else "")
            fig.add_trace(
                go.Bar(
                    name=method_short_label(method, settings),
                    x=xs,
                    y=ys,
                    marker=dict(color=method_color(method, settings)),
                    text=texts if show_text else None,
                    textposition="outside",
                )
            )
        x_title = "Resolution"
    fig.update_layout(
        **publication_layout(
            title=title,
            subtitle=subtitle,
            settings=settings,
            height=460,
            caption=direction_caption([metric]),
        ),
        barmode="group",
        xaxis=_xaxis(x_title, settings),
        yaxis=_yaxis(metric, settings),
    )
    _ = categories
    return fig


def build_slope(
    runs: Sequence[RunDTO],
    metric: str,
    settings: AppSettings,
    *,
    title: str,
    subtitle: str,
) -> go.Figure:
    fig = go.Figure()
    resolutions = _ordered_resolutions(runs, settings)
    for method in _ordered_methods(runs):
        xs, ys = [], []
        for res in resolutions:
            match = [
                r for r in runs if (r.method or "unknown") == method and r.resolution_label == res
            ]
            if not match or match[0].metric(metric) is None:
                continue
            xs.append(res)
            ys.append(match[0].metric(metric))
        if not xs:
            continue
        fig.add_trace(
            go.Scatter(
                name=method_short_label(method, settings),
                x=xs,
                y=ys,
                mode="lines+markers",
                line=dict(color=method_color(method, settings), width=2),
                marker=dict(size=9, color=method_color(method, settings)),
            )
        )
    fig.update_layout(
        **publication_layout(
            title=title,
            subtitle=subtitle,
            settings=settings,
            height=460,
            caption=direction_caption([metric]),
        ),
        xaxis=_xaxis("Resolution", settings),
        yaxis=_yaxis(metric, settings),
    )
    fig.update_xaxes(categoryorder="array", categoryarray=resolutions)
    return fig


def build_delta(
    runs: Sequence[RunDTO],
    metric: str,
    settings: AppSettings,
    *,
    baseline_method: str,
    title: str,
    subtitle: str,
) -> go.Figure:
    fig = go.Figure()
    resolutions = _ordered_resolutions(runs, settings)
    methods = [m for m in _ordered_methods(runs) if m != baseline_method]
    baseline_label = method_short_label(baseline_method, settings)
    for method in methods:
        xs, ys = [], []
        for res in resolutions:
            base = next(
                (
                    r
                    for r in runs
                    if (r.method or "unknown") == baseline_method and r.resolution_label == res
                ),
                None,
            )
            other = next(
                (
                    r
                    for r in runs
                    if (r.method or "unknown") == method and r.resolution_label == res
                ),
                None,
            )
            if base is None or other is None:
                continue
            bval, oval = base.metric(metric), other.metric(metric)
            if bval is None or oval is None:
                continue
            xs.append(res)
            ys.append(oval - bval)
        if not xs:
            continue
        fig.add_trace(
            go.Bar(
                name=f"{method_short_label(method, settings)} − {baseline_label}",
                x=xs,
                y=ys,
                marker=dict(color=method_color(method, settings)),
            )
        )
    spec = CATALOG.get(metric)
    caption = f"Signed delta versus {baseline_label}."
    if spec:
        caption += f" {spec.short_label}: {spec.better_hint}."
    fig.update_layout(
        **publication_layout(
            title=title,
            subtitle=subtitle,
            settings=settings,
            height=460,
            caption=caption,
        ),
        barmode="group",
        xaxis=_xaxis("Resolution", settings),
        yaxis=dict(
            title=dict(text=f"Δ {spec.short_label if spec else metric}", font=dict(size=13)),
            tickfont=dict(size=12),
            gridcolor=theme_colors(settings).grid,
            zeroline=True,
            zerolinecolor=theme_colors(settings).ink,
            zerolinewidth=1,
        ),
    )
    return fig


def build_radar(
    runs: Sequence[RunDTO],
    metrics: Sequence[str],
    settings: AppSettings,
    *,
    title: str,
    subtitle: str,
) -> go.Figure:
    keys = [k for k in metrics if k in CATALOG][:6]
    fig = go.Figure()
    subset = list(runs)[:6]
    for run in subset:
        values: list[float] = []
        for key in keys:
            spec = CATALOG[key]
            raw = run.metric(key)
            if raw is None:
                values.append(0)
                continue
            lo, hi = spec.typical_min, spec.typical_max
            span = hi - lo if hi != lo else 1.0
            norm = (raw - lo) / span
            norm = min(max(norm, 0.0), 1.0)
            if spec.direction == "lower":
                norm = 1.0 - norm
            values.append(norm)
        values.append(values[0] if values else 0)
        labels = [CATALOG[k].short_label for k in keys] + [CATALOG[keys[0]].short_label]
        fig.add_trace(
            go.Scatterpolar(
                r=values,
                theta=labels,
                fill="toself",
                name=friendly_run_name(run, settings),
                line=dict(color=_color_for(run, settings), width=1.5),
                opacity=0.75,
            )
        )
    colors = theme_colors(settings)
    fig.update_layout(
        **publication_layout(
            title=title,
            subtitle=subtitle,
            settings=settings,
            height=520,
            caption="Each axis is normalized 0–1 in the “better” direction. Use sparingly.",
        ),
        polar=dict(
            bgcolor=colors.paper,
            radialaxis=dict(
                visible=True, range=[0, 1], gridcolor=colors.grid, tickfont=dict(size=11)
            ),
            angularaxis=dict(tickfont=dict(size=12), linecolor=colors.line),
        ),
    )
    return fig


def build_compare_board(
    series: dict[str, list[RunDTO]],
    metrics: Sequence[str],
    settings: AppSettings,
    *,
    title: str,
    subtitle: str,
) -> go.Figure:
    """Cross-video small multiples aligned by method+resolution when possible."""
    keys = [k for k in metrics if k in CATALOG]
    n = len(keys)
    cols = 3 if n > 2 else max(n, 1)
    rows_n = (n + cols - 1) // cols if n else 1
    fig = make_subplots(
        rows=rows_n,
        cols=cols,
        subplot_titles=[f"{CATALOG[k].short_label} {CATALOG[k].arrow}" for k in keys],
        vertical_spacing=0.14,
        horizontal_spacing=0.08,
    )
    palette = ["#3D5C4A", "#E69F00", "#56B4E9", "#D55E00", "#0072B2", "#CC79A7"]
    video_ids = list(series.keys())
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
    labels = [f"{m}/{res}" for m, res in combos]
    for index, key in enumerate(keys):
        row = index // cols + 1
        col = index % cols + 1
        for v_i, video_id in enumerate(video_ids):
            runs = series[video_id]
            lookup = {(r.method or "unknown", r.resolution_label): r for r in runs}
            ys = []
            for pair in combos:
                run = lookup.get(pair)
                ys.append(run.metric(key) if run is not None else None)
            fig.add_trace(
                go.Scatter(
                    name=video_id,
                    x=labels,
                    y=ys,
                    mode="lines+markers",
                    marker=dict(
                        size=8,
                        color=palette[v_i % len(palette)],
                        symbol=RESOLUTION_SYMBOLS.get(combos[0][1], "circle")
                        if combos
                        else "circle",
                    ),
                    line=dict(color=palette[v_i % len(palette)], width=2),
                    legendgroup=video_id,
                    showlegend=(index == 0),
                ),
                row=row,
                col=col,
            )
        fig.update_xaxes(
            _xaxis("", settings),
            row=row,
            col=col,
            tickangle=-30,
            automargin=True,
        )
        fig.update_yaxes(_yaxis(key, settings), row=row, col=col)
    layout = publication_layout(
        title=title,
        subtitle=subtitle,
        settings=settings,
        height=320 * rows_n + 220,
        caption=direction_caption(keys),
        caption_yshift=-132,
    )
    layout["margin"]["b"] = 220
    fig.update_layout(**layout)
    return fig


def figure_for_type(
    chart_type: str,
    runs: Sequence[RunDTO],
    settings: AppSettings,
    *,
    title: str,
    subtitle: str,
    metrics: Sequence[str],
    baseline: str = "bicubic",
) -> go.Figure:
    hero = list(metrics) or list(settings.hero_metrics)
    primary = hero[0] if hero else "vmaf"
    if chart_type == "grouped_bar":
        return build_grouped_bar(runs, primary, settings, title=title, subtitle=subtitle)
    if chart_type == "slope":
        return build_slope(runs, primary, settings, title=title, subtitle=subtitle)
    if chart_type == "delta":
        return build_delta(
            runs, primary, settings, baseline_method=baseline, title=title, subtitle=subtitle
        )
    if chart_type == "radar":
        return build_radar(runs, hero, settings, title=title, subtitle=subtitle)
    return build_small_multiples(runs, hero, settings, title=title, subtitle=subtitle)
