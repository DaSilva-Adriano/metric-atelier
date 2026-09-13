from __future__ import annotations

from pathlib import Path

import pytest

from metric_atelier.grouping import friendly_run_name, sort_runs
from metric_atelier.ingest import CsvSource
from metric_atelier.metrics import flag_anomalous_runs
from metric_atelier.models import UNASSIGNED_VIDEO_ID, AppSettings
from metric_atelier.store import Store


def _source(path: Path) -> CsvSource:
    return CsvSource(name=path.name, content=path.read_bytes(), original_path=str(path))


def test_import_two_csvs_creates_two_videos(store: Store, samples_dir: Path) -> None:
    result = store.commit_sources(
        [_source(samples_dir / "beauty.csv"), _source(samples_dir / "kartingtime.csv")]
    )
    videos = {v.video_id: v for v in store.list_videos()}
    assert "beauty" in videos
    assert "kartingtime" in videos
    assert videos["beauty"].display_name == "Beauty"
    assert videos["kartingtime"].display_name == "Karting Time"
    beauty = store.list_runs("beauty")
    karting = store.list_runs("kartingtime")
    assert len(beauty) == 10
    assert len(karting) == 9
    assert {r.method for r in beauty if r.method} >= {"bicubic", "lanczos", "vsr"}
    assert {r.resolution_label for r in beauty} >= {"360p", "480p", "1080p", "2160p"}
    assert result.n_new == 19
    assert videos["kartingtime"].reference_width == 3840
    assert videos["kartingtime"].reference_height == 2160


def test_third_csv_merges_into_beauty(store: Store, samples_dir: Path, tmp_path: Path) -> None:
    store.commit_sources([_source(samples_dir / "beauty.csv")])
    extra = tmp_path / "beauty_more.csv"
    extra.write_text(
        "distorted,psnr_y,ssim_y,ms_ssim,vmaf,lpips,erqa,path,psnr_u,psnr_v,psnr_avg,"
        "ssim_u,ssim_v,ssim_all,vmaf_mean,vmaf_harmonic_mean,lpips_min,lpips_max,"
        "lpips_p50,lpips_p95,lpips_label,erqa_min,erqa_max,erqa_p50,erqa_p95,erqa_label,"
        "warnings,errors\n"
        "v-beauty-720p-24fps-vsr,32.1,0.91,0.95,71.4,0.16,0.70,C:\\x.mp4,,,,,,,,,,,,,,,,,,[],[]\n"
        "v-beauty-720p-24fps-bicubic,30.4,0.89,0.93,62.2,0.21,0.63,C:\\y.mp4,,,,,,,,,,,,,,,,,,[],[]\n",
        encoding="utf-8",
    )
    result = store.commit_sources([_source(extra)])
    assert result.affected_video_ids == ["beauty"]
    assert result.n_new == 2
    assert len(store.list_videos()) == 2  # beauty + unassigned
    runs = store.list_runs("beauty")
    assert len(runs) == 12
    assert any(r.resolution_label == "720p" and r.method == "vsr" for r in runs)


def test_reimport_same_file_does_not_duplicate(store: Store, samples_dir: Path) -> None:
    first = store.commit_sources([_source(samples_dir / "beauty.csv")])
    second = store.commit_sources([_source(samples_dir / "beauty.csv")])
    assert first.n_new == 10
    assert second.n_new == 0
    assert second.n_duplicate == 10
    assert len(store.list_runs("beauty")) == 10


def test_refresh_updates_metrics_preserves_notes(store: Store, tmp_path: Path) -> None:
    csv_path = tmp_path / "clip.csv"
    header = (
        "distorted,psnr_y,ssim_y,ms_ssim,vmaf,lpips,erqa,path,psnr_u,psnr_v,psnr_avg,"
        "ssim_u,ssim_v,ssim_all,vmaf_mean,vmaf_harmonic_mean,lpips_min,lpips_max,"
        "lpips_p50,lpips_p95,lpips_label,erqa_min,erqa_max,erqa_p50,erqa_p95,erqa_label,"
        "warnings,errors\n"
    )
    csv_path.write_text(
        header + "v-beauty-720p-24fps-vsr,30.0,0.90,0.94,70.0,0.20,0.70,/a.mp4," + "," * 18 + "\n",
        encoding="utf-8",
    )
    store.commit_sources([_source(csv_path)])
    run = store.list_runs("beauty")[0]
    store.update_run(run.run_id, notes="keep me", display_name="VSR 720p", hidden=True)

    csv_path.write_text(
        header + "v-beauty-720p-24fps-vsr,31.5,0.91,0.95,72.5,0.18,0.72,/a.mp4," + "," * 18 + "\n",
        encoding="utf-8",
    )
    skipped = store.commit_sources([_source(csv_path)], reimport_mode="skip")
    assert skipped.n_duplicate == 1
    still = store.get_run(run.run_id)
    assert still is not None
    assert still.psnr_y == 30.0
    assert still.notes == "keep me"

    refreshed = store.commit_sources([_source(csv_path)], reimport_mode="refresh")
    assert refreshed.n_refresh == 1
    updated = store.get_run(run.run_id)
    assert updated is not None
    assert updated.psnr_y == 31.5
    assert updated.vmaf == 72.5
    assert updated.notes == "keep me"
    assert updated.display_name == "VSR 720p"
    assert updated.hidden is True


def test_hide_is_not_delete(store: Store, samples_dir: Path) -> None:
    store.commit_sources([_source(samples_dir / "beauty.csv")])
    broken = next(r for r in store.list_runs("beauty") if r.psnr_y is not None and r.psnr_y < 20)
    store.set_hidden([broken.run_id], True)
    visible = store.list_runs("beauty", include_hidden=False)
    all_runs = store.list_runs("beauty", include_hidden=True)
    assert broken.run_id not in {r.run_id for r in visible}
    assert broken.run_id in {r.run_id for r in all_runs}
    store.set_hidden([broken.run_id], False)
    assert broken.run_id in {r.run_id for r in store.list_runs("beauty", include_hidden=False)}


def test_original_csv_not_rewritten(store: Store, tmp_path: Path) -> None:
    csv_path = tmp_path / "orig.csv"
    original = "distorted,psnr_y,vmaf\nv-beauty-360p-24fps-bicubic,27.4,48.2\n"
    csv_path.write_text(original, encoding="utf-8")
    store.import_paths([csv_path])
    store.update_run(store.list_runs("beauty")[0].run_id, notes="annotation")
    assert csv_path.read_text(encoding="utf-8") == original


def test_merge_and_move(store: Store, samples_dir: Path) -> None:
    store.commit_sources(
        [_source(samples_dir / "beauty.csv"), _source(samples_dir / "kartingtime.csv")]
    )
    moved = store.list_runs("kartingtime")[0]
    store.move_run(moved.run_id, "beauty")
    assert store.get_run(moved.run_id).video_id == "beauty"
    store.merge_videos("kartingtime", "beauty")
    ids = {v.video_id for v in store.list_videos()}
    assert "kartingtime" not in ids
    assert all(r.video_id == "beauty" for r in store.list_runs("beauty"))


def test_soft_outlier_flag_on_broken_vsr(store: Store, samples_dir: Path) -> None:
    store.commit_sources([_source(samples_dir / "beauty.csv")])
    runs = store.list_runs("beauty", include_hidden=True)
    payload = [{"run_id": r.run_id, "metrics": r.metrics_dict(), "errors": r.errors} for r in runs]
    flags = flag_anomalous_runs(payload)
    broken = next(
        r for r in runs if r.raw_name.endswith("1080p-24fps-vsr") and r.psnr_y and r.psnr_y < 20
    )
    assert broken.run_id in flags


def test_sort_by_resolution(store: Store, samples_dir: Path) -> None:
    store.commit_sources([_source(samples_dir / "beauty.csv")])
    settings = AppSettings()
    ordered = sort_runs(
        store.list_runs("beauty", include_hidden=True), how="resolution", settings=settings
    )
    labels = [r.resolution_label for r in ordered if r.resolution_label != "unknown"]
    assert labels == sorted(
        labels,
        key=lambda x: settings.resolution_order.index(x) if x in settings.resolution_order else 99,
    )
    name = friendly_run_name(ordered[0], settings)
    assert name
    assert UNASSIGNED_VIDEO_ID in {v.video_id for v in store.list_videos()}


def test_update_run_cannot_change_metric_numbers(store: Store, samples_dir: Path) -> None:
    store.commit_sources([_source(samples_dir / "beauty.csv")])
    run = store.list_runs("beauty")[0]
    original_vmaf = run.vmaf
    original_psnr = run.psnr_y
    store.update_run(run.run_id, vmaf=0.0, psnr_y=1.0, notes="annotation only")
    updated = store.get_run(run.run_id)
    assert updated is not None
    assert updated.vmaf == original_vmaf
    assert updated.psnr_y == original_psnr
    assert updated.notes == "annotation only"


def test_purge_run_removes_row(store: Store, samples_dir: Path) -> None:
    store.commit_sources([_source(samples_dir / "beauty.csv")])
    before = store.list_runs("beauty")
    target = before[0]
    removed = store.purge_runs([target.run_id])
    assert removed == 1
    assert store.get_run(target.run_id) is None
    assert len(store.list_runs("beauty")) == len(before) - 1


def test_delete_video_removes_library_source(store: Store, samples_dir: Path) -> None:
    store.commit_sources(
        [_source(samples_dir / "beauty.csv"), _source(samples_dir / "kartingtime.csv")]
    )
    n = store.delete_video("beauty")
    assert n == 10
    assert store.get_video("beauty") is None
    assert store.list_runs("beauty") == []
    assert store.get_video("kartingtime") is not None
    assert len(store.list_runs("kartingtime")) == 9


def test_cannot_delete_unassigned_group(store: Store) -> None:
    with pytest.raises(ValueError):
        store.delete_video(UNASSIGNED_VIDEO_ID)
    assert store.get_video(UNASSIGNED_VIDEO_ID) is not None


def test_dataset_json_uses_method_and_resolution_fields(store: Store, samples_dir: Path) -> None:
    store.commit_sources([_source(samples_dir / "beauty.csv")])
    payload = store.export_dataset("beauty")
    assert payload["kind"] == "metric-atelier-dataset"
    assert payload["version"] == 2
    video = payload["videos"][0]
    assert video["video_id"] == "beauty"
    assert video["runs"]
    vsr = next(run for run in video["runs"] if run.get("method_key") == "vsr")
    assert vsr["method"] == "VSR"
    assert vsr["method_key"] == "vsr"
    assert vsr["method_raw"]
    assert vsr["name"]
    assert vsr["resolution"] in {"360p", "480p", "1080p", "2160p"}
    assert isinstance(vsr["metrics"], dict)
    assert "vmaf" in vsr["metrics"] or "psnr_y" in vsr["metrics"]
    for run in video["runs"]:
        assert "method" in run
        assert "resolution" in run
        assert "metrics" in run
        assert isinstance(run["metrics"], dict)
        assert run["raw_name"], "raw_name is a label only; method/resolution are the fields"


def test_dataset_json_method_follows_display_toggle(store: Store, tmp_path: Path) -> None:
    csv_path = tmp_path / "clip.csv"
    csv_path.write_text(
        "distorted,vmaf,psnr_y\n"
        "v-clip-1080p-24fps-ANIMEJANAI_BAL_V3,80.0,32.0\n"
        "v-clip-1080p-24fps-FSRCNNX8,70.0,30.0\n",
        encoding="utf-8",
    )
    store.commit_sources([_source(csv_path)])
    store.update_settings(show_full_method_name=False)
    hidden = store.export_dataset("clip")
    methods = {row["method_key"]: row for row in hidden["videos"][0]["runs"]}
    assert methods["animejanai_bal"]["method"] == "ANIMEJANAI_BAL"
    assert methods["animejanai_bal"]["name"].startswith("ANIMEJANAI_BAL")
    assert methods["fsrcnnx8"]["method"] == "FSRCNNX8"
    store.update_settings(show_full_method_name=True)
    shown = store.export_dataset("clip")
    full = next(row for row in shown["videos"][0]["runs"] if row["method_key"] == "animejanai_bal")
    assert full["method"] == "ANIMEJANAI_BAL_V3"
    assert "ANIMEJANAI_BAL_V3" in full["name"]
