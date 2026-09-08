from __future__ import annotations

from pathlib import Path

from metric_atelier.ingest import parse_csv_bytes, parse_list_field, to_optional_float
from metric_atelier.metrics import format_metric

CSV_HEADER = (
    "distorted,psnr_y,ssim_y,ms_ssim,vmaf,lpips,erqa,path,psnr_u,psnr_v,psnr_avg,"
    "ssim_u,ssim_v,ssim_all,vmaf_mean,vmaf_harmonic_mean,lpips_min,lpips_max,"
    "lpips_p50,lpips_p95,lpips_label,erqa_min,erqa_max,erqa_p50,erqa_p95,erqa_label,"
    "warnings,errors"
)


def test_parse_list_field_stringified_python_list() -> None:
    assert parse_list_field("['resolution mismatch', 'skipped PSNR']") == [
        "resolution mismatch",
        "skipped PSNR",
    ]
    assert parse_list_field("[]") == []
    assert parse_list_field(None) == []
    assert parse_list_field("plain warning") == ["plain warning"]


def test_to_optional_float_empty() -> None:
    assert to_optional_float("") is None
    assert to_optional_float("nan") is None
    assert to_optional_float(None) is None
    assert to_optional_float("30.36") == 30.36


def _row(**values: object) -> str:
    import csv
    from io import StringIO

    columns = CSV_HEADER.split(",")
    record = {key: "" for key in columns}
    record.update({key: values[key] for key in values})
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    writer.writerow(record)
    return buffer.getvalue()


def test_incomplete_row_does_not_crash() -> None:
    body = _row(
        distorted="v-beauty-2160p-24fps-vsr",
        path=r"C:\clips\x.mp4",
        warnings="[]",
        errors="['resolution mismatch: 1920x1080 vs 3840x2160']",
    )
    rows = parse_csv_bytes(body.encode("utf-8"))
    assert len(rows) == 1
    row = rows[0]
    assert row.metrics["psnr_y"] is None
    assert row.metrics["vmaf"] is None
    assert row.errors
    assert "resolution mismatch" in row.errors[0]
    assert row.parsed.video_id == "beauty"


def test_extra_columns_preserved() -> None:
    body = (
        CSV_HEADER
        + ",future_metric\n"
        + "v-beauty-360p-24fps-bicubic,27.4,0.84,0.90,48.2,0.31,0.52,"
        + r"C:\x.mp4"
        + ",36.1,36.4,33.3,0.96,0.96,0.89,48.2,47.0,0.24,0.44,0.30,0.40,lpips-vgg,"
        + "0.40,0.66,0.52,0.61,erqa,[],[],0.123\n"
    )
    rows = parse_csv_bytes(body.encode("utf-8"))
    assert rows[0].extra_columns.get("future_metric") not in (None, "")


def test_windows_path_kept() -> None:
    path = r"C:\Users\adri1\tests\beauty\v-beauty-360p-24fps-bicubic.mp4"
    body = (
        CSV_HEADER
        + "\n"
        + f"v-beauty-360p-24fps-bicubic,27.4,0.84,0.90,48.2,0.31,0.52,{path},"
        + "," * 18
        + "\n"
    )
    rows = parse_csv_bytes(body.encode("utf-8"))
    assert rows[0].path == path


def test_format_metric_never_float_soup() -> None:
    assert format_metric("vmaf", 30.363285714285713) == "30.4"
    assert format_metric("psnr_y", 30.363285714285713) == "30.36"
    assert format_metric("ssim_y", 0.942857142) == "0.943"
    assert format_metric("lpips", None) == "—"


def test_sample_csvs_parse(samples_dir: Path) -> None:
    beauty = parse_csv_bytes((samples_dir / "beauty.csv").read_bytes(), source_name="beauty.csv")
    karting = parse_csv_bytes(
        (samples_dir / "kartingtime.csv").read_bytes(), source_name="kartingtime.csv"
    )
    assert {row.parsed.video_id for row in beauty} == {"beauty"}
    assert {row.parsed.video_id for row in karting} == {"kartingtime"}
    methods = {row.parsed.method for row in beauty if row.parsed.method}
    assert {"bicubic", "lanczos", "vsr"} <= methods
    assert any(row.errors for row in beauty)
    assert any(
        row.parsed.resolution_label == "1080p"
        and row.metrics.get("psnr_y")
        and row.metrics["psnr_y"] < 20
        for row in beauty
    )
