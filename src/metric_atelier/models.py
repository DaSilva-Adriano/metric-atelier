"""Pydantic settings / DTOs and SQLModel persistence tables."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Column, DateTime, Float
from sqlalchemy.types import JSON
from sqlmodel import Field as SQLField
from sqlmodel import SQLModel

from metric_atelier.metrics import DEFAULT_DECIMALS, DEFAULT_HERO_METRICS, DEFAULT_Y_AXIS_ZERO

UNASSIGNED_VIDEO_ID = "unassigned"

ReimportMode = Literal["skip", "refresh"]
ThemeName = Literal["light", "dark"]
ColorBy = Literal["method", "resolution"]
ChartType = Literal["small_multiples", "grouped_bar", "slope", "delta", "radar"]
ExportBackground = Literal["white", "theme"]


def utcnow() -> datetime:
    return datetime.now(UTC)


class IdentityRule(BaseModel):
    """Override: this distorted name belongs to video X."""

    pattern: str
    video_id: str
    display_name: str | None = None
    is_regex: bool = False


class AppSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    theme: ThemeName = "light"
    accent_color: str = "#3D5C4A"
    font_scale: int = 100
    presentation_mode: bool = False
    decimal_places: dict[str, int] = Field(default_factory=lambda: dict(DEFAULT_DECIMALS))
    hero_metrics: list[str] = Field(default_factory=lambda: list(DEFAULT_HERO_METRICS))
    method_colors: dict[str, str] = Field(default_factory=dict)
    method_display_aliases: dict[str, str] = Field(
        default_factory=lambda: {
            "vsr": "VSR",
            "bicubic": "Bicubic",
            "lanczos": "Lanczos",
            "bilinear": "Bilinear",
            "nearest": "Nearest",
            "esrgan": "ESRGAN",
            "realesrgan": "Real-ESRGAN",
            "swinir": "SwinIR",
            "basicvsr": "BasicVSR",
            "ia": "IA",
            "native": "Native",
        }
    )
    extra_method_aliases: dict[str, str] = Field(default_factory=dict)
    resolution_order: list[str] = Field(
        default_factory=lambda: ["360p", "480p", "720p", "1080p", "1440p", "2160p"]
    )
    show_raw_filenames: bool = False
    language: str = "en"

    reimport_mode: ReimportMode = "skip"
    identity_rules: list[IdentityRule] = Field(default_factory=list)
    extra_parser_regexes: list[str] = Field(default_factory=list)

    default_chart_type: ChartType = "small_multiples"
    show_bar_values: bool = True
    y_axis_zero: dict[str, bool] = Field(default_factory=lambda: dict(DEFAULT_Y_AXIS_ZERO))
    color_by: ColorBy = "method"
    export_scale: int = 2
    export_background: ExportBackground = "white"
    export_width: int = 2000

    reveal_hidden: bool = False
    visible_columns: list[str] = Field(
        default_factory=lambda: [
            "visible",
            "name",
            "method",
            "resolution",
            "fps",
            "vmaf",
            "psnr_y",
            "ssim_y",
            "ms_ssim",
            "lpips",
            "erqa",
            "status",
            "notes",
        ]
    )


class SourceVideo(SQLModel, table=True):
    __tablename__ = "source_videos"

    video_id: str = SQLField(primary_key=True)
    display_name: str
    notes: str = ""
    tags: list[str] = SQLField(default_factory=list, sa_column=Column(JSON, nullable=False))
    sort_index: int = 0
    reference_width: int | None = None
    reference_height: int | None = None
    reference_fps: float | None = None
    reference_color: str | None = None
    reference_bits: int | None = None
    chart_title: str | None = None
    chart_caption: str | None = None
    created_at: datetime = SQLField(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = SQLField(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class RunRecord(SQLModel, table=True):
    __tablename__ = "runs"

    run_id: str = SQLField(primary_key=True, max_length=64)
    path_key: str = SQLField(index=True)
    video_id: str = SQLField(index=True, foreign_key="source_videos.video_id")
    raw_name: str = SQLField(index=True)
    source_csv: str = ""
    source_basename: str = ""
    snapshot_path: str = ""
    file_hash: str = SQLField(index=True)
    row_index: int = 0
    imported_at: datetime = SQLField(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    batch_tag: str | None = None
    method: str | None = None
    method_raw: str | None = None
    method_known: bool = False
    resolution_label: str = "unknown"
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    source_width: int | None = None
    source_height: int | None = None
    source_fps: float | None = None
    source_color: str | None = None
    source_bits: int | None = None
    leftovers: str | None = None

    psnr_y: float | None = SQLField(default=None, sa_column=Column(Float, nullable=True))
    ssim_y: float | None = None
    ms_ssim: float | None = None
    vmaf: float | None = None
    lpips: float | None = None
    erqa: float | None = None
    psnr_u: float | None = None
    psnr_v: float | None = None
    psnr_avg: float | None = None
    ssim_u: float | None = None
    ssim_v: float | None = None
    ssim_all: float | None = None
    vmaf_mean: float | None = None
    vmaf_harmonic_mean: float | None = None
    lpips_min: float | None = None
    lpips_max: float | None = None
    lpips_p50: float | None = None
    lpips_p95: float | None = None
    erqa_min: float | None = None
    erqa_max: float | None = None
    erqa_p50: float | None = None
    erqa_p95: float | None = None
    lpips_label: str | None = None
    erqa_label: str | None = None

    extra_columns: dict[str, Any] = SQLField(default_factory=dict, sa_column=Column(JSON))
    warnings: list[str] = SQLField(default_factory=list, sa_column=Column(JSON))
    errors: list[str] = SQLField(default_factory=list, sa_column=Column(JSON))
    path: str | None = None

    hidden: bool = False
    display_name: str | None = None
    notes: str = ""
    sort_index: int = 0
    color: str | None = None
    deleted_at: datetime | None = None


class ImportedFile(SQLModel, table=True):
    __tablename__ = "imported_files"

    file_hash: str = SQLField(primary_key=True)
    original_path: str = ""
    snapshot_path: str = ""
    basename: str = ""
    imported_at: datetime = SQLField(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    n_rows: int = 0


class SettingsRow(SQLModel, table=True):
    __tablename__ = "settings"

    id: int = SQLField(default=1, primary_key=True)
    payload: dict[str, Any] = SQLField(default_factory=dict, sa_column=Column(JSON, nullable=False))


class VideoSummary(BaseModel):
    video_id: str
    display_name: str
    notes: str = ""
    tags: list[str] = Field(default_factory=list)
    sort_index: int = 0
    n_runs: int = 0
    n_hidden: int = 0
    n_deleted: int = 0
    n_errors: int = 0
    n_warnings: int = 0
    methods: list[str] = Field(default_factory=list)
    resolutions: list[str] = Field(default_factory=list)
    last_import: datetime | None = None
    reference_label: str = ""
    is_unassigned: bool = False


class RunDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    run_id: str
    path_key: str
    video_id: str
    raw_name: str
    source_csv: str = ""
    source_basename: str = ""
    snapshot_path: str = ""
    file_hash: str = ""
    row_index: int = 0
    imported_at: datetime | None = None
    batch_tag: str | None = None
    method: str | None = None
    method_raw: str | None = None
    method_known: bool = False
    resolution_label: str = "unknown"
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    source_width: int | None = None
    source_height: int | None = None
    source_fps: float | None = None
    source_color: str | None = None
    source_bits: int | None = None
    leftovers: str | None = None
    psnr_y: float | None = None
    ssim_y: float | None = None
    ms_ssim: float | None = None
    vmaf: float | None = None
    lpips: float | None = None
    erqa: float | None = None
    psnr_u: float | None = None
    psnr_v: float | None = None
    psnr_avg: float | None = None
    ssim_u: float | None = None
    ssim_v: float | None = None
    ssim_all: float | None = None
    vmaf_mean: float | None = None
    vmaf_harmonic_mean: float | None = None
    lpips_min: float | None = None
    lpips_max: float | None = None
    lpips_p50: float | None = None
    lpips_p95: float | None = None
    erqa_min: float | None = None
    erqa_max: float | None = None
    erqa_p50: float | None = None
    erqa_p95: float | None = None
    lpips_label: str | None = None
    erqa_label: str | None = None
    extra_columns: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    path: str | None = None
    hidden: bool = False
    display_name: str | None = None
    notes: str = ""
    sort_index: int = 0
    color: str | None = None
    deleted_at: datetime | None = None

    def metric(self, key: str) -> float | None:
        return getattr(self, key, None) if hasattr(self, key) else self.extra_columns.get(key)

    def metrics_dict(self) -> dict[str, float | None]:
        from metric_atelier.metrics import KNOWN_METRIC_COLUMNS

        return {key: getattr(self, key) for key in KNOWN_METRIC_COLUMNS}


METRIC_FIELD_NAMES = (
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
