from __future__ import annotations

from metric_atelier.metrics import (
    ALL_METRICS_KEY,
    CATALOG,
    DEFAULT_HERO_METRICS,
    direction_caption,
    format_metric,
    format_threshold_input,
    metric_choice_options,
    parse_threshold_list,
    resolve_metric_choice,
    threshold_status,
)
from metric_atelier.models import AppSettings


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


def test_metric_choice_all_or_specific() -> None:
    options = metric_choice_options(["vmaf", "psnr_y", "lpips"])
    assert options[ALL_METRICS_KEY] == "All metrics"
    assert options["vmaf"] == "VMAF"
    assert options["psnr_y"] == "PSNR-Y"
    assert resolve_metric_choice(ALL_METRICS_KEY, ["vmaf", "psnr_y"]) == ["vmaf", "psnr_y"]
    assert resolve_metric_choice("vmaf", ["vmaf", "psnr_y"]) == ["vmaf"]
    assert resolve_metric_choice(None, ["vmaf", "psnr_y"]) == ["vmaf", "psnr_y"]
    assert resolve_metric_choice("missing", ["vmaf", "psnr_y"]) == ["vmaf", "psnr_y"]


def test_threshold_status_respects_direction() -> None:
    thresholds = {"vmaf": 80.0, "lpips": 0.2}
    assert threshold_status("vmaf", 90.0, thresholds) == "pass"
    assert threshold_status("vmaf", 70.0, thresholds) == "fail"
    assert threshold_status("lpips", 0.1, thresholds) == "pass"
    assert threshold_status("lpips", 0.4, thresholds) == "fail"
    assert threshold_status("vmaf", 90.0, {}) == "none"
    assert threshold_status("vmaf", None, thresholds) == "none"


def test_parse_threshold_list_splits_on_comma() -> None:
    assert parse_threshold_list("80, 90, 95") == [80.0, 90.0, 95.0]
    assert parse_threshold_list("80,90") == [80.0, 90.0]
    assert parse_threshold_list("80, , 90") == [80.0, 90.0]
    assert parse_threshold_list("80, 80, 90") == [80.0, 90.0]
    assert parse_threshold_list(80) == [80.0]
    assert parse_threshold_list([70, "80"]) == [70.0, 80.0]
    assert parse_threshold_list("") == []
    assert parse_threshold_list("nope") == []
    assert format_threshold_input([80.0, 90.5]) == "80, 90.5"


def test_threshold_status_uses_most_lenient_of_several() -> None:
    thresholds = {"vmaf": [80.0, 90.0, 95.0], "lpips": [0.1, 0.2]}
    assert threshold_status("vmaf", 85.0, thresholds) == "pass"
    assert threshold_status("vmaf", 70.0, thresholds) == "fail"
    assert threshold_status("lpips", 0.15, thresholds) == "pass"
    assert threshold_status("lpips", 0.4, thresholds) == "fail"


def test_settings_coerce_legacy_single_threshold() -> None:
    settings = AppSettings(metric_thresholds={"vmaf": 80.0, "psnr_y": "32, 35"})
    assert settings.metric_thresholds["vmaf"] == [80.0]
    assert settings.metric_thresholds["psnr_y"] == [32.0, 35.0]
