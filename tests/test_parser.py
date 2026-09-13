from __future__ import annotations

from metric_atelier.grouping import method_display_label
from metric_atelier.ingest import (
    IdentityRule,
    ParserContext,
    parse_filename,
    slug_video_id,
    title_to_display,
)
from metric_atelier.models import UNASSIGNED_VIDEO_ID, AppSettings


def test_pattern_a_karting_time() -> None:
    parsed = parse_filename("s-KartingTime_3840x2160_60fps_yuv444_16bits_70-720p-60fps-vsr")
    assert parsed.prefix == "s"
    assert parsed.title == "KartingTime"
    assert parsed.display_title == "Karting Time"
    assert parsed.video_id == "kartingtime"
    assert parsed.method == "vsr"
    assert parsed.method_known is True
    assert parsed.resolution_label == "720p"
    assert parsed.width == 1280
    assert parsed.height == 720
    assert parsed.fps == 60
    assert parsed.source_width == 3840
    assert parsed.source_height == 2160
    assert parsed.source_fps == 60
    assert parsed.source_color == "yuv444"
    assert parsed.source_bits == 16
    assert parsed.leftovers == "70"
    assert parsed.unassigned is False


def test_pattern_b_beauty_variants() -> None:
    bicubic = parse_filename("v-beauty-360p-24fps-bicubic")
    assert bicubic.prefix == "v"
    assert bicubic.title.lower() == "beauty"
    assert bicubic.display_title == "Beauty"
    assert bicubic.video_id == "beauty"
    assert bicubic.method == "bicubic"
    assert bicubic.resolution_label == "360p"
    assert bicubic.fps == 24
    assert bicubic.source_width is None

    lanczos = parse_filename("v-beauty-480p-24fps-lanczos")
    assert lanczos.method == "lanczos"
    assert lanczos.resolution_label == "480p"
    assert lanczos.video_id == "beauty"

    vsr = parse_filename("v-beauty-1080p-24fps-vsr")
    assert vsr.method == "vsr"
    assert vsr.resolution_label == "1080p"
    assert vsr.video_id == "beauty"


def test_same_title_same_video_id() -> None:
    a = parse_filename("v-beauty-360p-24fps-bicubic")
    b = parse_filename("v-Beauty-1080p-24fps-vsr")
    c = parse_filename("beauty-720p-lanczos")
    assert a.video_id == b.video_id == c.video_id == "beauty"


def test_karting_time_slug_stable() -> None:
    a = parse_filename("s-KartingTime_3840x2160_60fps_yuv444_16bits_70-720p-60fps-vsr")
    b = parse_filename("v-karting_time-1080p-60fps-bicubic")
    assert a.video_id == b.video_id == "kartingtime"


def test_animejanai_bal_is_registered_full_name() -> None:
    parsed = parse_filename("v-clip-1080p-24fps-ANIMEJANAI_BAL")
    assert parsed.method == "animejanai_bal"
    assert parsed.method_known is True
    assert parsed.method_raw == "animejanai_bal"
    settings = AppSettings()
    assert method_display_label(parsed.method, settings, method_raw=parsed.method_raw) == (
        "ANIMEJANAI_BAL"
    )


def test_unregistered_suffix_hidden_unless_full_name_toggle() -> None:
    parsed = parse_filename("v-clip-1080p-24fps-ANIMEJANAI_BAL_V3")
    assert parsed.method == "animejanai_bal"
    assert parsed.method_raw.lower() == "animejanai_bal_v3"
    assert parsed.method_raw.endswith("V3")
    assert parsed.method_known is True
    hidden = AppSettings(show_full_method_name=False)
    shown = AppSettings(show_full_method_name=True)
    assert (
        method_display_label(parsed.method, hidden, method_raw=parsed.method_raw)
        == "ANIMEJANAI_BAL"
    )
    assert (
        method_display_label(parsed.method, shown, method_raw=parsed.method_raw)
        == "ANIMEJANAI_BAL_V3"
    )


def test_fsrcnnx_methods() -> None:
    eight = parse_filename("v-clip-720p-24fps-FSRCNNX8")
    sixteen = parse_filename("v-clip-720p-24fps-FSRCNNX16")
    assert eight.method == "fsrcnnx8"
    assert sixteen.method == "fsrcnnx16"
    settings = AppSettings()
    assert method_display_label(eight.method, settings, method_raw=eight.method_raw) == "FSRCNNX8"
    assert (
        method_display_label(sixteen.method, settings, method_raw=sixteen.method_raw) == "FSRCNNX16"
    )


def test_unregistered_underscore_uses_first_part() -> None:
    parsed = parse_filename("v-clip-720p-24fps-foo_bar")
    assert parsed.method == "foo_bar"
    assert parsed.method_known is False
    hidden = AppSettings(show_full_method_name=False)
    shown = AppSettings(show_full_method_name=True)
    assert method_display_label(parsed.method, hidden, method_raw=parsed.method_raw) == "foo"
    assert method_display_label(parsed.method, shown, method_raw=parsed.method_raw) == "foo_bar"


def test_unknown_method_kept_as_raw_token() -> None:
    parsed = parse_filename("v-beauty-720p-24fps-splatting")
    assert parsed.method == "splatting"
    assert parsed.method_known is False
    assert parsed.video_id == "beauty"


def test_native_aliases() -> None:
    for token in ("native", "none", "raw"):
        parsed = parse_filename(f"v-beauty-2160p-24fps-{token}")
        assert parsed.method == "native"


def test_method_aliases() -> None:
    assert parse_filename("v-clip-720p-realesrgan").method == "realesrgan"
    assert parse_filename("v-clip-720p-real-esrgan").method == "realesrgan"
    assert parse_filename("v-clip-720p-nn").method == "nearest"
    ctx = ParserContext(extra_method_aliases={"cubic": "bicubic"})
    assert parse_filename("v-clip-720p-cubic", ctx).method == "bicubic"


def test_4k_token_normalizes_to_2160p() -> None:
    parsed = parse_filename("v-beauty-4k-24fps-native")
    assert parsed.resolution_label == "2160p"


def test_wxh_only_is_target() -> None:
    parsed = parse_filename("v-scene-1920x1080-30fps-lanczos")
    assert parsed.resolution_label == "1080p"
    assert parsed.width == 1920
    assert parsed.height == 1080
    assert parsed.source_width is None


def test_missing_method_is_allowed() -> None:
    parsed = parse_filename("v-beauty-1080p-24fps")
    assert parsed.method is None
    assert parsed.resolution_label == "1080p"
    assert parsed.video_id == "beauty"


def test_unassigned_when_no_title() -> None:
    parsed = parse_filename("720p-24fps-vsr")
    assert parsed.unassigned is True
    assert parsed.video_id == UNASSIGNED_VIDEO_ID


def test_no_prefix_still_parses() -> None:
    parsed = parse_filename("beauty-360p-24fps-bicubic")
    assert parsed.prefix is None
    assert parsed.video_id == "beauty"
    assert parsed.method == "bicubic"


def test_title_to_display_camel_case() -> None:
    assert title_to_display("KartingTime") == "Karting Time"
    assert title_to_display("beauty") == "Beauty"
    assert title_to_display("BigBuckBunny") == "Big Buck Bunny"
    assert slug_video_id("KartingTime") == "kartingtime"


def test_identity_rule_overrides_video() -> None:
    ctx = ParserContext(
        identity_rules=[
            IdentityRule(pattern="karting", video_id="kartingtime", display_name="Karting Time")
        ]
    )
    parsed = parse_filename("mystery-clip-720p-vsr", ctx)
    assert parsed.video_id == "mysteryclip"
    forced = parse_filename("s-something_karting_special-720p-vsr", ctx)
    assert forced.video_id == "kartingtime"
    assert forced.display_title == "Karting Time"


def test_extra_regex_named_groups() -> None:
    ctx = ParserContext(
        extra_parser_regexes=[r"(?P<title>clip\d+)-(?P<res>\d+p)-(?P<method>vsr|bicubic)"]
    )
    parsed = parse_filename("clip12-1080p-vsr", ctx)
    assert parsed.title == "clip12"
    assert parsed.video_id == "clip12"
    assert parsed.resolution_label == "1080p"
    assert parsed.method == "vsr"


def test_uppercase_prefix_and_fps() -> None:
    parsed = parse_filename("S-DemoClip_1280x720_30FPS_yuv420_8bits-480p-30FPS-LANCZOS")
    assert parsed.prefix == "s"
    assert parsed.method == "lanczos"
    assert parsed.fps == 30
    assert parsed.video_id == "democlip"
