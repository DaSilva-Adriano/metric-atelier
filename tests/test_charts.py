from __future__ import annotations

from pathlib import Path

from metric_atelier.charts import figure_for_type, order_runs_for_chart
from metric_atelier.export import comparison_payload
from metric_atelier.ingest import CsvSource
from metric_atelier.models import AppSettings
from metric_atelier.store import Store


def _source(path: Path) -> CsvSource:
    return CsvSource(name=path.name, content=path.read_bytes(), original_path=str(path))


def test_chart_value_order_sorts_runs(store: Store, samples_dir: Path) -> None:
    store.commit_sources([_source(samples_dir / "beauty.csv")])
    settings = AppSettings()
    runs = [run for run in store.list_runs("beauty") if run.vmaf is not None]
    asc = order_runs_for_chart(runs, settings, how="value_asc", metric="vmaf")
    desc = order_runs_for_chart(runs, settings, how="value_desc", metric="vmaf")
    asc_vals = [run.vmaf for run in asc if run.vmaf is not None]
    desc_vals = [run.vmaf for run in desc if run.vmaf is not None]
    assert asc_vals == sorted(asc_vals)
    assert desc_vals == sorted(desc_vals, reverse=True)


def test_ranked_bar_respects_custom_order(store: Store, samples_dir: Path) -> None:
    store.commit_sources([_source(samples_dir / "beauty.csv")])
    settings = AppSettings()
    runs = [run for run in store.list_runs("beauty") if not run.errors]
    reversed_ids = list(reversed([run.run_id for run in runs]))
    store.reorder_runs(reversed_ids)
    ordered = store.list_runs("beauty")
    visible = [run for run in ordered if not run.errors]
    fig = figure_for_type(
        "ranked_bar",
        visible,
        settings,
        title="t",
        subtitle="s",
        metrics=["vmaf"],
        order="table",
    )
    assert list(fig.data[0].x)[0]  # labels present
    table_order = order_runs_for_chart(visible, settings, how="table", metric="vmaf")
    assert [run.run_id for run in table_order] == [run.run_id for run in visible]


def test_new_chart_types_build(store: Store, samples_dir: Path) -> None:
    store.commit_sources([_source(samples_dir / "beauty.csv")])
    settings = AppSettings(metric_thresholds={"vmaf": 80.0})
    runs = [run for run in store.list_runs("beauty") if not run.hidden]
    for chart_type in (
        "small_multiples",
        "grouped_bar",
        "slope",
        "ranked_bar",
        "horizontal_bar",
        "heatmap",
        "scatter",
        "radar",
    ):
        fig = figure_for_type(
            chart_type,
            runs,
            settings,
            title="t",
            subtitle="s",
            metrics=["vmaf", "psnr_y"],
            order="value_desc",
        )
        assert fig.data


def test_grouped_bar_specific_metric_uses_that_axis(store: Store, samples_dir: Path) -> None:
    store.commit_sources([_source(samples_dir / "beauty.csv")])
    settings = AppSettings()
    runs = [run for run in store.list_runs("beauty") if not run.hidden]
    fig = figure_for_type(
        "grouped_bar",
        runs,
        settings,
        title="t",
        subtitle="s",
        metrics=["psnr_y"],
    )
    title = fig.layout.yaxis.title.text or ""
    assert "PSNR" in title
    assert "VMAF" not in title


def test_grouped_bar_all_metrics_builds_a_panel_per_metric(store: Store, samples_dir: Path) -> None:
    store.commit_sources([_source(samples_dir / "beauty.csv")])
    settings = AppSettings()
    runs = [run for run in store.list_runs("beauty") if not run.hidden]
    fig = figure_for_type(
        "grouped_bar",
        runs,
        settings,
        title="t",
        subtitle="s",
        metrics=["vmaf", "psnr_y", "ssim_y"],
    )
    assert fig.layout.yaxis is not None
    assert fig.layout.yaxis2 is not None
    assert fig.layout.yaxis3 is not None
    titles = [
        (fig.layout.annotations[i].text if i < len(fig.layout.annotations) else "")
        for i in range(3)
    ]
    joined = " ".join(titles)
    assert "VMAF" in joined
    assert "PSNR" in joined


def test_small_multiples_one_metric_is_a_single_panel(store: Store, samples_dir: Path) -> None:
    store.commit_sources([_source(samples_dir / "beauty.csv")])
    settings = AppSettings()
    runs = [run for run in store.list_runs("beauty") if not run.hidden]
    fig = figure_for_type(
        "small_multiples",
        runs,
        settings,
        title="t",
        subtitle="s",
        metrics=["vmaf"],
    )
    assert fig.data
    assert getattr(fig.layout, "yaxis2", None) is None or fig.layout.yaxis2.domain is None


def test_comparison_json_covers_multiple_contents(store: Store, samples_dir: Path) -> None:
    store.commit_sources(
        [_source(samples_dir / "beauty.csv"), _source(samples_dir / "kartingtime.csv")]
    )
    settings = AppSettings()
    beauty = store.get_video("beauty")
    karting = store.get_video("kartingtime")
    assert beauty is not None and karting is not None
    series = {
        beauty.display_name: [run for run in store.list_runs("beauty") if not run.hidden],
        karting.display_name: [run for run in store.list_runs("kartingtime") if not run.hidden],
    }
    payload = comparison_payload(
        series,
        settings,
        metrics=["vmaf", "psnr_y"],
        contents=[
            {"video_id": "beauty", "display_name": beauty.display_name},
            {"video_id": "kartingtime", "display_name": karting.display_name},
        ],
    )
    assert payload["kind"] == "metric-atelier-comparison"
    assert payload["metrics"] == ["vmaf", "psnr_y"]
    assert [item["video_id"] for item in payload["contents"]] == ["beauty", "kartingtime"]
    assert payload["rows"]
    matched = [row for row in payload["rows"] if row["by_content"]["beauty"] is not None]
    assert matched
    sample = matched[0]["by_content"]["beauty"]
    assert "metrics" in sample
    assert "vmaf" in sample["metrics"] or "psnr_y" in sample["metrics"]
    assert "resolution" in sample
