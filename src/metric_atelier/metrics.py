"""Metric catalog, directions, number formatting, and soft outlier flags."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from statistics import median
from typing import Literal

Direction = Literal["higher", "lower"]
Family = Literal["fidelity", "perceptual-score", "perceptual-distance", "reconstruction"]


@dataclass(frozen=True, slots=True)
class MetricSpec:
    key: str
    short_label: str
    long_label: str
    direction: Direction
    family: Family
    decimals: int
    typical_min: float
    typical_max: float
    hero: bool = False
    missing_ok_with_errors: bool = True

    @property
    def better_hint(self) -> str:
        return "↑ better" if self.direction == "higher" else "↓ better"

    @property
    def arrow(self) -> str:
        return "↑" if self.direction == "higher" else "↓"


KNOWN_METRIC_COLUMNS: tuple[str, ...] = (
    "psnr_y",
    "ssim_y",
    "ms_ssim",
    "vmaf",
    "lpips",
    "erqa",
    "psnr_u",
    "psnr_v",
    "psnr_avg",
    "ssim_u",
    "ssim_v",
    "ssim_all",
    "vmaf_mean",
    "vmaf_harmonic_mean",
    "lpips_min",
    "lpips_max",
    "lpips_p50",
    "lpips_p95",
    "erqa_min",
    "erqa_max",
    "erqa_p50",
    "erqa_p95",
)

LABEL_COLUMNS: tuple[str, ...] = ("lpips_label", "erqa_label")

CORE_COLUMNS: tuple[str, ...] = (
    "distorted",
    "path",
    "warnings",
    "errors",
    *KNOWN_METRIC_COLUMNS,
    *LABEL_COLUMNS,
)

DEFAULT_HERO_METRICS: tuple[str, ...] = (
    "vmaf",
    "psnr_y",
    "ssim_y",
    "ms_ssim",
    "lpips",
    "erqa",
)

SECONDARY_METRICS: tuple[str, ...] = (
    "psnr_u",
    "psnr_v",
    "psnr_avg",
    "ssim_u",
    "ssim_v",
    "ssim_all",
    "vmaf_mean",
    "vmaf_harmonic_mean",
    "lpips_min",
    "lpips_max",
    "lpips_p50",
    "lpips_p95",
    "erqa_min",
    "erqa_max",
    "erqa_p50",
    "erqa_p95",
)


def _spec(
    key: str,
    short: str,
    long: str,
    direction: Direction,
    family: Family,
    decimals: int,
    lo: float,
    hi: float,
    *,
    hero: bool = False,
) -> MetricSpec:
    return MetricSpec(
        key=key,
        short_label=short,
        long_label=long,
        direction=direction,
        family=family,
        decimals=decimals,
        typical_min=lo,
        typical_max=hi,
        hero=hero,
    )


CATALOG: dict[str, MetricSpec] = {
    spec.key: spec
    for spec in (
        _spec(
            "vmaf",
            "VMAF",
            "Video Multi-method Assessment Fusion",
            "higher",
            "perceptual-score",
            1,
            0,
            100,
            hero=True,
        ),
        _spec(
            "psnr_y",
            "PSNR-Y",
            "Peak Signal-to-Noise Ratio (luma)",
            "higher",
            "fidelity",
            2,
            0,
            60,
            hero=True,
        ),
        _spec(
            "ssim_y",
            "SSIM-Y",
            "Structural Similarity (luma)",
            "higher",
            "fidelity",
            3,
            0,
            1,
            hero=True,
        ),
        _spec(
            "ms_ssim",
            "MS-SSIM",
            "Multi-Scale Structural Similarity",
            "higher",
            "fidelity",
            3,
            0,
            1,
            hero=True,
        ),
        _spec(
            "lpips",
            "LPIPS",
            "Learned Perceptual Image Patch Similarity",
            "lower",
            "perceptual-distance",
            3,
            0,
            1,
            hero=True,
        ),
        _spec(
            "erqa",
            "ERQA",
            "Edge Restoration Quality Assessment",
            "lower",
            "reconstruction",
            3,
            0,
            1,
            hero=True,
        ),
        _spec("psnr_u", "PSNR-U", "Peak Signal-to-Noise Ratio (U)", "higher", "fidelity", 2, 0, 60),
        _spec("psnr_v", "PSNR-V", "Peak Signal-to-Noise Ratio (V)", "higher", "fidelity", 2, 0, 60),
        _spec(
            "psnr_avg",
            "PSNR-avg",
            "Peak Signal-to-Noise Ratio (average)",
            "higher",
            "fidelity",
            2,
            0,
            60,
        ),
        _spec("ssim_u", "SSIM-U", "Structural Similarity (U)", "higher", "fidelity", 3, 0, 1),
        _spec("ssim_v", "SSIM-V", "Structural Similarity (V)", "higher", "fidelity", 3, 0, 1),
        _spec(
            "ssim_all",
            "SSIM-all",
            "Structural Similarity (all planes)",
            "higher",
            "fidelity",
            3,
            0,
            1,
        ),
        _spec("vmaf_mean", "VMAF mean", "VMAF (mean)", "higher", "perceptual-score", 1, 0, 100),
        _spec(
            "vmaf_harmonic_mean",
            "VMAF H-mean",
            "VMAF (harmonic mean)",
            "higher",
            "perceptual-score",
            1,
            0,
            100,
        ),
        _spec("lpips_min", "LPIPS min", "LPIPS (minimum)", "lower", "perceptual-distance", 3, 0, 1),
        _spec("lpips_max", "LPIPS max", "LPIPS (maximum)", "lower", "perceptual-distance", 3, 0, 1),
        _spec("lpips_p50", "LPIPS p50", "LPIPS (median)", "lower", "perceptual-distance", 3, 0, 1),
        _spec(
            "lpips_p95",
            "LPIPS p95",
            "LPIPS (95th percentile)",
            "lower",
            "perceptual-distance",
            3,
            0,
            1,
        ),
        _spec("erqa_min", "ERQA min", "ERQA (minimum)", "lower", "reconstruction", 3, 0, 1),
        _spec("erqa_max", "ERQA max", "ERQA (maximum)", "lower", "reconstruction", 3, 0, 1),
        _spec("erqa_p50", "ERQA p50", "ERQA (median)", "lower", "reconstruction", 3, 0, 1),
        _spec("erqa_p95", "ERQA p95", "ERQA (95th percentile)", "lower", "reconstruction", 3, 0, 1),
    )
}

DEFAULT_DECIMALS: dict[str, int] = {key: spec.decimals for key, spec in CATALOG.items()}

DEFAULT_Y_AXIS_ZERO: dict[str, bool] = {
    "vmaf": False,
    "vmaf_mean": False,
    "vmaf_harmonic_mean": False,
    "psnr_y": False,
    "psnr_u": False,
    "psnr_v": False,
    "psnr_avg": False,
    "ssim_y": False,
    "ssim_u": False,
    "ssim_v": False,
    "ssim_all": False,
    "ms_ssim": False,
    "lpips": False,
    "lpips_min": False,
    "lpips_max": False,
    "lpips_p50": False,
    "lpips_p95": False,
    "erqa": False,
    "erqa_min": False,
    "erqa_max": False,
    "erqa_p50": False,
    "erqa_p95": False,
}

LOWER_IS_BETTER: frozenset[str] = frozenset(
    key for key, spec in CATALOG.items() if spec.direction == "lower"
)


ALL_METRICS_KEY = "all"


def get_spec(key: str) -> MetricSpec | None:
    return CATALOG.get(key)


def metric_choice_options(keys: Sequence[str] | None = None) -> dict[str, str]:
    """Select options: All metrics, then each hero (or provided) metric."""
    options = {ALL_METRICS_KEY: "All metrics"}
    for key in keys or DEFAULT_HERO_METRICS:
        spec = CATALOG.get(key)
        options[key] = spec.short_label if spec else key
    return options


def resolve_metric_choice(
    choice: str | None,
    keys: Sequence[str] | None = None,
) -> list[str]:
    """Map All / a specific metric onto the list of keys a chart should plot."""
    available = [key for key in (keys or DEFAULT_HERO_METRICS) if key in CATALOG]
    if not available:
        available = list(DEFAULT_HERO_METRICS)
    if not choice or choice == ALL_METRICS_KEY:
        return list(available)
    if choice in available:
        return [choice]
    if choice in CATALOG:
        return [choice]
    return list(available)


def threshold_status(
    key: str,
    value: float | None,
    thresholds: Mapping[str, float] | None,
) -> Literal["pass", "fail", "none"]:
    """Compare a value to a user threshold. Empty/missing threshold → none."""
    if value is None or not thresholds or key not in thresholds:
        return "none"
    try:
        limit = float(thresholds[key])
        number = float(value)
    except (TypeError, ValueError):
        return "none"
    if number != number or limit != limit:
        return "none"
    spec = CATALOG.get(key)
    if spec is not None and spec.direction == "lower":
        return "fail" if number > limit else "pass"
    return "fail" if number < limit else "pass"


def threshold_failed(
    key: str,
    value: float | None,
    thresholds: Mapping[str, float] | None,
) -> bool:
    return threshold_status(key, value, thresholds) == "fail"


def format_metric(
    key: str,
    value: float | None,
    *,
    decimals: Mapping[str, int] | None = None,
    empty: str = "—",
) -> str:
    """Format a metric for humans. Never emit raw float soup."""
    if value is None:
        return empty
    try:
        if value != value:  # NaN
            return empty
    except Exception:
        return empty
    spec = CATALOG.get(key)
    places = (decimals or {}).get(key) if decimals is not None else None
    if places is None:
        places = spec.decimals if spec is not None else 3
    return f"{value:.{places}f}"


def column_label(key: str, *, with_hint: bool = True) -> str:
    spec = CATALOG.get(key)
    if spec is None:
        return key
    if with_hint:
        return f"{spec.short_label} {spec.arrow}"
    return spec.short_label


def direction_caption(keys: Sequence[str]) -> str:
    """Footer copy. Two lines so it never runs into axis labels."""
    higher = [
        CATALOG[k].short_label for k in keys if k in CATALOG and CATALOG[k].direction == "higher"
    ]
    lower = [
        CATALOG[k].short_label for k in keys if k in CATALOG and CATALOG[k].direction == "lower"
    ]
    lines: list[str] = []
    if higher:
        lines.append(f"↑ higher is better — {', '.join(higher)}")
    if lower:
        lines.append(f"↓ lower is better — {', '.join(lower)}")
    return "<br>".join(lines)


def _finite(values: Iterable[float | None]) -> list[float]:
    out: list[float] = []
    for value in values:
        if value is None:
            continue
        try:
            if value == value:
                out.append(float(value))
        except (TypeError, ValueError):
            continue
    return out


def flag_anomalous_runs(
    runs: Sequence[Mapping[str, object]],
    *,
    psnr_key: str = "psnr_y",
    vmaf_key: str = "vmaf",
) -> dict[str, list[str]]:
    """Soft-flag runs that look collapsed versus siblings. Never auto-hide."""
    flags: dict[str, list[str]] = {}
    if len(runs) < 3:
        return flags

    def metric_of(run: Mapping[str, object], key: str) -> float | None:
        metrics = run.get("metrics")
        if isinstance(metrics, Mapping) and key in metrics:
            value = metrics.get(key)
        else:
            value = run.get(key)
        if value is None:
            return None
        try:
            number = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None
        if number != number:
            return None
        return number

    psnrs = _finite(metric_of(run, psnr_key) for run in runs)
    vmafs = _finite(metric_of(run, vmaf_key) for run in runs)
    if len(psnrs) < 3 and len(vmafs) < 3:
        return flags

    med_p = median(psnrs) if psnrs else None
    med_v = median(vmafs) if vmafs else None

    def mad(values: list[float], med: float) -> float:
        return median([abs(v - med) for v in values]) if values else 0.0

    mad_p = mad(psnrs, med_p) if med_p is not None else 0.0
    mad_v = mad(vmafs, med_v) if med_v is not None else 0.0

    for run in runs:
        run_id = str(run.get("run_id") or "")
        if not run_id:
            continue
        errors = run.get("errors") or []
        if errors:
            continue
        psnr = metric_of(run, psnr_key)
        vmaf = metric_of(run, vmaf_key)
        reasons: list[str] = []

        collapsed = (
            med_p is not None
            and med_v is not None
            and psnr is not None
            and vmaf is not None
            and med_p >= 28
            and psnr < 20
            and med_v >= 55
            and vmaf < 40
        )
        if collapsed:
            reasons.append(
                "Looks collapsed versus siblings (e.g. failed reconstruct). "
                "Do not treat this row as a fair method comparison."
            )

        def is_outlier(value: float | None, med: float | None, scatter: float) -> bool:
            if value is None or med is None:
                return False
            if scatter < 1e-6:
                return abs(value - med) > max(8.0 if med > 20 else 0.15, 0.25 * abs(med))
            z = 0.6745 * (value - med) / scatter
            return abs(z) > 3.5 and abs(value - med) > 0.25 * max(abs(med), 1.0)

        if not collapsed and (is_outlier(psnr, med_p, mad_p) or is_outlier(vmaf, med_v, mad_v)):
            reasons.append("Outlier versus other runs of this video — double-check the encode.")

        if reasons:
            flags[run_id] = reasons
    return flags
