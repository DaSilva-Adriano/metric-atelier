from __future__ import annotations

from metric_atelier.metrics import (
    CATALOG,
    DEFAULT_HERO_METRICS,
    direction_caption,
    format_metric,
    threshold_status,
)


def test_hero_metrics_present() -> None:
    for key in DEFAULT_HERO_METRICS:
        assert key in CATALOG
    assert CATALOG["vmaf"].direction == "higher"
    assert CATALOG["lpips"].direction == "lower"
    assert CATALOG["erqa"].direction == "lower"


def test_direction_caption() -> None:
    text = direction_caption(["vmaf", "psnr_y", "lpips", "erqa"])
    assert "higher is better" in text
    assert "lower is better" in text
    assert "LPIPS" in text


def test_format_none() -> None:
    assert format_metric("vmaf", None) == "—"
    assert format_metric("unknown_metric", 1.23456) == "1.235"


def test_threshold_status_respects_direction() -> None:
    thresholds = {"vmaf": 80.0, "lpips": 0.2}
    assert threshold_status("vmaf", 90.0, thresholds) == "pass"
    assert threshold_status("vmaf", 70.0, thresholds) == "fail"
    assert threshold_status("lpips", 0.1, thresholds) == "pass"
    assert threshold_status("lpips", 0.4, thresholds) == "fail"
    assert threshold_status("vmaf", 90.0, {}) == "none"
    assert threshold_status("vmaf", None, thresholds) == "none"
