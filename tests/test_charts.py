from __future__ import annotations

from pathlib import Path

from metric_atelier.charts import figure_for_type, order_runs_for_chart
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
