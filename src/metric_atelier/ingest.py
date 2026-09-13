"""CSV import and filename parser.

Never mutates original CSV files. Parsing is pure; persistence lives in store.py.
"""

from __future__ import annotations

import ast
import hashlib
import math
import re
from dataclasses import dataclass, field
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel, Field

from metric_atelier.metrics import CORE_COLUMNS, KNOWN_METRIC_COLUMNS, LABEL_COLUMNS
from metric_atelier.models import UNASSIGNED_VIDEO_ID, IdentityRule

KNOWN_METHODS: dict[str, str] = {
    "vsr": "vsr",
    "bicubic": "bicubic",
    "lanczos": "lanczos",
    "bilinear": "bilinear",
    "nearest": "nearest",
    "nn": "nearest",
    "esrgan": "esrgan",
    "realesrgan": "realesrgan",
    "real-esrgan": "realesrgan",
    "real_esrgan": "realesrgan",
    "swinir": "swinir",
    "basicvsr": "basicvsr",
    "basicvsr++": "basicvsr",
    "basicvsrpp": "basicvsr",
    "ia": "ia",
    "none": "native",
    "native": "native",
    "raw": "native",
    "animejanai_bal": "animejanai_bal",
    "fsrcnnx8": "fsrcnnx8",
    "fsrcnnx_8": "fsrcnnx8",
    "fsrcnnx16": "fsrcnnx16",
    "fsrcnnx_16": "fsrcnnx16",
}

RESOLUTION_LABELS: dict[str, str] = {
    "360p": "360p",
    "480p": "480p",
    "720p": "720p",
    "1080p": "1080p",
    "1440p": "1440p",
    "2160p": "2160p",
    "4k": "2160p",
}

HEIGHT_TO_LABEL: dict[int, str] = {
    360: "360p",
    480: "480p",
    720: "720p",
    1080: "1080p",
    1440: "1440p",
    2160: "2160p",
}

LABEL_TO_SIZE: dict[str, tuple[int, int]] = {
    "360p": (640, 360),
    "480p": (854, 480),
    "720p": (1280, 720),
    "1080p": (1920, 1080),
    "1440p": (2560, 1440),
    "2160p": (3840, 2160),
}

PREFIX_RE = re.compile(r"^(?P<prefix>[sv])-(?P<rest>.+)$", re.IGNORECASE)
WXH_RE = re.compile(r"^(?P<w>\d{3,5})x(?P<h>\d{3,5})$", re.IGNORECASE)
FPS_RE = re.compile(r"^(?P<fps>\d+(?:\.\d+)?)(?:fps|hz)$", re.IGNORECASE)
P_RES_RE = re.compile(r"^(?P<label>\d{3,4}p|4k)$", re.IGNORECASE)
YUV_RE = re.compile(r"^yuv[\w]+$", re.IGNORECASE)
BITS_RE = re.compile(r"^(?P<bits>\d+)(?:bits?)$", re.IGNORECASE)
TOKEN_SPLIT_RE = re.compile(r"[-_]+")
CAMEL_RE = re.compile(r"([a-z0-9])([A-Z])")
ACRONYM_RE = re.compile(r"([A-Z]+)([A-Z][a-z])")
STRIP_EXTS = (".csv", ".yuv", ".mp4", ".mkv", ".mov", ".avi", ".webm", ".y4m")


class ParserContext(BaseModel):
    extra_method_aliases: dict[str, str] = Field(default_factory=dict)
    identity_rules: list[IdentityRule] = Field(default_factory=list)
    extra_parser_regexes: list[str] = Field(default_factory=list)


class ParsedFilename(BaseModel):
    raw: str
    prefix: str | None = None
    title: str = ""
    display_title: str = ""
    video_id: str = UNASSIGNED_VIDEO_ID
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
    unassigned: bool = False


class ParsedRow(BaseModel):
    row_index: int
    distorted: str
    parsed: ParsedFilename
    metrics: dict[str, float | None] = Field(default_factory=dict)
    labels: dict[str, str | None] = Field(default_factory=dict)
    extra_columns: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    path: str | None = None


class CsvSource(BaseModel):
    name: str
    content: bytes
    original_path: str | None = None


PreviewStatus = Literal["new", "duplicate", "refresh", "unassigned", "error"]


class PreviewRow(BaseModel):
    row_index: int
    raw_name: str
    video_id: str
    video_display: str
    method: str | None = None
    resolution_label: str = "unknown"
    status: PreviewStatus
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    run_id: str
    path_key: str


class ImportPreview(BaseModel):
    files: list[str]
    rows: list[PreviewRow]
    n_new: int = 0
    n_duplicate: int = 0
    n_refresh: int = 0
    n_assigned: int = 0
    n_unassigned: int = 0
    n_errors: int = 0


class ImportResult(BaseModel):
    n_new: int = 0
    n_duplicate: int = 0
    n_refresh: int = 0
    n_unassigned: int = 0
    n_errors: int = 0
    new_run_ids: list[str] = Field(default_factory=list)
    affected_video_ids: list[str] = Field(default_factory=list)


@dataclass
class _Token:
    kind: str
    value: Any
    raw: str


def method_alias_map(extra: dict[str, str] | None = None) -> dict[str, str]:
    mapping = dict(KNOWN_METHODS)
    if extra:
        for alias, target in extra.items():
            key = alias.strip().lower()
            canon = str(target).strip().lower()
            mapping[key] = mapping.get(canon, canon)
    return mapping


def slug_video_id(title: str) -> str:
    display = title_to_display(title)
    slug = re.sub(r"[^a-z0-9]+", "", display.lower())
    return slug or UNASSIGNED_VIDEO_ID


def title_to_display(title: str) -> str:
    text = title.strip()
    if not text:
        return ""
    text = CAMEL_RE.sub(r"\1 \2", text)
    text = ACRONYM_RE.sub(r"\1 \2", text)
    text = text.replace("_", " ").replace("-", " ")
    text = re.sub(r"\s+", " ", text).strip()
    parts = [part[:1].upper() + part[1:] if part else part for part in text.split(" ")]
    return " ".join(parts)


def _strip_extension(name: str) -> str:
    stem = name.strip()
    lower = stem.lower()
    for ext in STRIP_EXTS:
        if lower.endswith(ext):
            return stem[: -len(ext)]
    return stem


def _coalesce_tokens(tokens: list[str]) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(tokens):
        current = tokens[i]
        nxt = tokens[i + 1] if i + 1 < len(tokens) else None
        nxt2 = tokens[i + 2] if i + 2 < len(tokens) else None
        if (
            nxt is not None
            and current.replace(".", "", 1).isdigit()
            and nxt.lower() in {"fps", "hz"}
        ):
            out.append(f"{current}fps")
            i += 2
            continue
        if nxt is not None and current.isdigit() and nxt.lower() in {"bit", "bits"}:
            out.append(f"{current}bits")
            i += 2
            continue
        if nxt == "x" and nxt2 is not None and current.isdigit() and nxt2.isdigit():
            out.append(f"{current}x{nxt2}")
            i += 3
            continue
        out.append(current)
        i += 1
    return out


def _coalesce_method_phrases(tokens: list[str], methods: dict[str, str]) -> list[str]:
    """Join split tokens that together form an alias (real-esrgan, basicvsr++)."""
    phrases = sorted(
        (key for key in methods if "-" in key or "_" in key or "+" in key),
        key=len,
        reverse=True,
    )
    if not phrases:
        return tokens
    lowered = [token.lower() for token in tokens]
    out: list[str] = []
    index = 0
    while index < len(tokens):
        matched = False
        for phrase in phrases:
            parts = re.split(r"[-_]", phrase)
            width = len(parts)
            if width >= 2 and lowered[index : index + width] == parts:
                out.append(phrase)
                index += width
                matched = True
                break
        if not matched:
            out.append(tokens[index])
            index += 1
    return out


def _pick_method(
    spec_tokens: list[_Token], methods: dict[str, str]
) -> tuple[str | None, str | None, bool, set[int]]:
    """Return canonical method, raw token (with suffix), known flag, consumed spec indices."""
    known = set(methods.values())
    method_indices = [i for i, tok in enumerate(spec_tokens) if tok.kind == "method"]
    consumed: set[int] = set()
    if method_indices:
        last_i = method_indices[-1]
        method = str(spec_tokens[last_i].value)
        method_raw = str(spec_tokens[last_i].raw).lower()
        j = last_i + 1
        extra: list[str] = []
        while j < len(spec_tokens) and spec_tokens[j].kind == "name":
            extra.append(str(spec_tokens[j].raw))
            consumed.add(j)
            j += 1
        if extra:
            method_raw = method_raw + "_" + "_".join(extra)
        return method, method_raw, method in known, consumed

    trailing: list[int] = []
    for index in range(len(spec_tokens) - 1, -1, -1):
        if spec_tokens[index].kind == "name":
            trailing.append(index)
        else:
            break
    trailing.reverse()
    if not trailing:
        return None, None, False, consumed
    method_raw = "_".join(str(spec_tokens[i].raw) for i in trailing)
    consumed.update(trailing)
    raw_low = method_raw.lower()
    registered = None
    for key in sorted(known, key=len, reverse=True):
        if raw_low == key or raw_low.startswith(key + "_"):
            registered = key
            break
    if registered:
        return registered, method_raw, True, consumed
    return raw_low, method_raw, raw_low in known, consumed


def _classify(token: str, methods: dict[str, str]) -> _Token:
    low = token.lower()
    if low in methods:
        return _Token("method", methods[low], token)
    match = P_RES_RE.fullmatch(token)
    if match:
        label = RESOLUTION_LABELS.get(match.group("label").lower(), match.group("label").lower())
        return _Token("res_label", label, token)
    match = WXH_RE.fullmatch(token)
    if match:
        return _Token("wxh", (int(match.group("w")), int(match.group("h"))), token)
    match = FPS_RE.fullmatch(token)
    if match:
        return _Token("fps", float(match.group("fps")), token)
    if YUV_RE.fullmatch(token):
        return _Token("color", token.lower(), token)
    match = BITS_RE.fullmatch(token)
    if match:
        return _Token("bits", int(match.group("bits")), token)
    if token.isdigit() and 1 <= len(token) <= 4:
        return _Token("leftover", token, token)
    return _Token("name", token, token)


def _apply_user_regexes(stem: str, patterns: list[str]) -> dict[str, str]:
    for pattern in patterns:
        if not pattern or not pattern.strip():
            continue
        try:
            match = re.search(pattern, stem)
        except re.error:
            continue
        if not match:
            continue
        groups = {k: v for k, v in match.groupdict().items() if v is not None and v != ""}
        if groups:
            return groups
    return {}


def _apply_identity_rules(parsed: ParsedFilename, rules: list[IdentityRule]) -> ParsedFilename:
    haystacks = [parsed.raw, parsed.title, parsed.display_title]
    for rule in rules:
        pattern = rule.pattern.strip()
        if not pattern:
            continue
        matched = False
        if rule.is_regex:
            try:
                matched = any(re.search(pattern, item or "", re.IGNORECASE) for item in haystacks)
            except re.error:
                matched = False
        else:
            needle = pattern.lower()
            matched = any(needle in (item or "").lower() for item in haystacks)
        if matched and rule.video_id:
            parsed.video_id = (
                slug_video_id(rule.video_id) if " " in rule.video_id else rule.video_id
            )
            parsed.unassigned = parsed.video_id == UNASSIGNED_VIDEO_ID
            if rule.display_name:
                parsed.display_title = rule.display_name
            return parsed
    return parsed


def _label_from_height(height: int | None) -> str:
    if height is None:
        return "unknown"
    return HEIGHT_TO_LABEL.get(height, "unknown")


def parse_filename(raw: str, ctx: ParserContext | None = None) -> ParsedFilename:
    """Parse a distorted clip filename. Does not assume a single pattern."""
    ctx = ctx or ParserContext()
    original = (raw or "").strip()
    stem = _strip_extension(original)
    methods = method_alias_map(ctx.extra_method_aliases)
    user = _apply_user_regexes(stem, ctx.extra_parser_regexes)

    prefix: str | None = None
    rest = stem
    match = PREFIX_RE.match(stem)
    if match:
        prefix = match.group("prefix").lower()
        rest = match.group("rest")

    tokens = _coalesce_method_phrases(
        _coalesce_tokens([t for t in TOKEN_SPLIT_RE.split(rest) if t]),
        methods,
    )
    classified = [_classify(token, methods) for token in tokens]
    first_spec = next(
        (i for i, tok in enumerate(classified) if tok.kind != "name"), len(classified)
    )
    title_tokens = [tok.value for tok in classified[:first_spec] if tok.kind == "name"]
    spec_tokens = classified[first_spec:]

    method, method_raw, method_known, consumed_method = _pick_method(spec_tokens, methods)
    name_in_specs = [
        tok.value
        for i, tok in enumerate(spec_tokens)
        if tok.kind == "name" and i not in consumed_method
    ]

    res_labels = [tok.value for tok in spec_tokens if tok.kind == "res_label"]
    wxhs = [tok.value for tok in spec_tokens if tok.kind == "wxh"]
    fpss = [tok.value for tok in spec_tokens if tok.kind == "fps"]
    colors = [tok.value for tok in spec_tokens if tok.kind == "color"]
    bits_vals = [tok.value for tok in spec_tokens if tok.kind == "bits"]
    leftovers = [str(tok.value) for tok in spec_tokens if tok.kind == "leftover"]
    leftovers.extend(str(n) for n in name_in_specs)

    if not fpss:
        maybe_fps = [item for item in leftovers if item.isdigit() and 12 <= int(item) <= 120]
        if maybe_fps:
            chosen = maybe_fps[-1]
            fpss = [float(chosen)]
            leftovers = [item for item in leftovers if item != chosen]

    source_width = source_height = None
    width = height = None
    resolution_label = "unknown"

    if wxhs and res_labels:
        source_width, source_height = wxhs[0]
        resolution_label = res_labels[-1]
        width, height = LABEL_TO_SIZE.get(resolution_label, (None, None))
        if len(wxhs) > 1:
            width, height = wxhs[-1]
            resolution_label = (
                _label_from_height(height) if resolution_label == "unknown" else resolution_label
            )
    elif res_labels:
        resolution_label = res_labels[-1]
        width, height = LABEL_TO_SIZE.get(resolution_label, (None, None))
        if len(res_labels) > 1:
            src_label = res_labels[0]
            source_width, source_height = LABEL_TO_SIZE.get(src_label, (None, None))
    elif wxhs:
        if len(wxhs) == 1:
            width, height = wxhs[0]
            resolution_label = _label_from_height(height)
        else:
            source_width, source_height = wxhs[0]
            width, height = wxhs[-1]
            resolution_label = _label_from_height(height)

    source_fps = fpss[0] if len(fpss) > 1 else None
    fps = fpss[-1] if fpss else None

    title = " ".join(str(t) for t in title_tokens).strip()
    # Prefer the raw camelCase token for display splitting when a single token.
    if len(title_tokens) == 1:
        title = str(title_tokens[0])
    display = title_to_display(title)
    video_id = slug_video_id(title) if title else UNASSIGNED_VIDEO_ID
    unassigned = video_id == UNASSIGNED_VIDEO_ID or not title

    parsed = ParsedFilename(
        raw=original,
        prefix=prefix,
        title=title,
        display_title=display or "Unassigned",
        video_id=UNASSIGNED_VIDEO_ID if unassigned else video_id,
        method=method,
        method_raw=method_raw,
        method_known=method_known,
        resolution_label=resolution_label if not unassigned or resolution_label else "unknown",
        width=width,
        height=height,
        fps=fps,
        source_width=source_width,
        source_height=source_height,
        source_fps=source_fps,
        source_color=colors[0] if colors else None,
        source_bits=bits_vals[0] if bits_vals else None,
        leftovers=" ".join(leftovers) if leftovers else None,
        unassigned=unassigned,
    )

    if user:
        if "prefix" in user:
            parsed.prefix = user["prefix"].lower()
        if "title" in user:
            parsed.title = user["title"]
            parsed.display_title = title_to_display(user["title"])
            parsed.video_id = slug_video_id(user["title"])
            parsed.unassigned = parsed.video_id == UNASSIGNED_VIDEO_ID
        if "method" in user:
            alias = methods.get(user["method"].lower(), user["method"].lower())
            parsed.method = alias
            parsed.method_raw = user["method"].lower()
            parsed.method_known = (
                alias in set(methods.values()) and user["method"].lower() in methods
            )
        if "resolution" in user or "res" in user:
            token = user.get("resolution") or user.get("res") or ""
            classified_res = _classify(token, methods)
            if classified_res.kind == "res_label":
                parsed.resolution_label = classified_res.value
                parsed.width, parsed.height = LABEL_TO_SIZE.get(classified_res.value, (None, None))
            elif classified_res.kind == "wxh":
                parsed.width, parsed.height = classified_res.value
                parsed.resolution_label = _label_from_height(parsed.height)
        if "fps" in user:
            try:
                parsed.fps = float(str(user["fps"]).lower().replace("fps", ""))
            except ValueError:
                pass
        if "width" in user:
            try:
                parsed.width = int(user["width"])
            except ValueError:
                pass
        if "height" in user:
            try:
                parsed.height = int(user["height"])
            except ValueError:
                pass

    parsed = _apply_identity_rules(parsed, ctx.identity_rules)
    if parsed.unassigned:
        parsed.video_id = UNASSIGNED_VIDEO_ID
        if not parsed.display_title:
            parsed.display_title = "Unassigned"
    return parsed


def to_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return None
        return number
    text = str(value).strip()
    if text == "" or text.lower() in {"nan", "none", "null", "na", "<na>"}:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def parse_list_field(value: Any) -> list[str]:
    """Accept real lists or stringified Python lists from CSV cells."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, float) and math.isnan(value):
        return []
    text = str(value).strip()
    if text == "" or text.lower() in {"nan", "none", "null", "[]"}:
        return []
    try:
        parsed = ast.literal_eval(text)
    except (ValueError, SyntaxError):
        return [text]
    if isinstance(parsed, (list, tuple)):
        return [str(item).strip() for item in parsed if str(item).strip()]
    if parsed is None:
        return []
    return [str(parsed).strip()]


def file_fingerprint(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def make_run_id(file_hash: str, row_index: int, distorted: str) -> str:
    payload = f"{file_hash}:{row_index}:{distorted}".encode()
    return hashlib.sha256(payload).hexdigest()[:32]


def make_path_key(path: str, row_index: int, distorted: str) -> str:
    normalized = str(Path(path)) if path else ""
    try:
        normalized = str(Path(normalized).expanduser())
    except Exception:
        pass
    payload = f"{normalized.casefold()}:{row_index}:{distorted}".encode()
    return hashlib.sha256(payload).hexdigest()[:32]


def parse_csv_bytes(content: bytes, *, source_name: str = "upload.csv") -> list[ParsedRow]:
    """Parse a quality-summary CSV. Incomplete rows are kept, never crashed on."""
    text: str
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            text = content.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = content.decode("utf-8", errors="replace")

    try:
        frame = pd.read_csv(StringIO(text), dtype=object, keep_default_na=True)
    except Exception:
        frame = pd.read_csv(BytesIO(content), dtype=object, keep_default_na=True)

    frame.columns = [str(col).strip() for col in frame.columns]
    rows: list[ParsedRow] = []
    known = set(CORE_COLUMNS)

    for index, record in frame.iterrows():
        data = {str(k): record[k] for k in frame.columns}
        distorted_raw = data.get("distorted")
        distorted = "" if _is_blank(distorted_raw) else str(distorted_raw).strip()
        parsed = parse_filename(distorted) if distorted else ParsedFilename(raw="", unassigned=True)
        if not distorted:
            parsed.unassigned = True
            parsed.video_id = UNASSIGNED_VIDEO_ID
            parsed.display_title = "Unassigned"

        metrics = {key: to_optional_float(data.get(key)) for key in KNOWN_METRIC_COLUMNS}
        labels = {
            key: (None if _is_blank(data.get(key)) else str(data.get(key)).strip())
            for key in LABEL_COLUMNS
        }
        extra = {key: _cell_to_jsonable(value) for key, value in data.items() if key not in known}
        path_val = data.get("path")
        path = None if _is_blank(path_val) else str(path_val)
        warnings = parse_list_field(data.get("warnings"))
        errors = parse_list_field(data.get("errors"))
        if not distorted:
            errors = [*errors, "missing distorted filename"]

        rows.append(
            ParsedRow(
                row_index=int(index),
                distorted=distorted or f"{source_name}:row{index}",
                parsed=parsed,
                metrics=metrics,
                labels=labels,
                extra_columns=extra,
                warnings=warnings,
                errors=errors,
                path=path,
            )
        )
    return rows


def parse_csv_path(
    path: Path, *, ctx: ParserContext | None = None
) -> tuple[bytes, list[ParsedRow]]:
    content = Path(path).read_bytes()
    rows = parse_csv_bytes(content, source_name=Path(path).name)
    if ctx is not None:
        for row in rows:
            row.parsed = parse_filename(row.distorted, ctx)
    return content, rows


def apply_parser_context(rows: list[ParsedRow], ctx: ParserContext) -> list[ParsedRow]:
    for row in rows:
        row.parsed = parse_filename(row.distorted, ctx)
    return rows


def collect_csv_paths(path: Path) -> list[Path]:
    target = Path(path)
    if target.is_file() and target.suffix.lower() == ".csv":
        return [target]
    if target.is_dir():
        return sorted({*target.glob("*.csv"), *target.glob("**/*.csv")})
    return []


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    text = str(value).strip()
    return text == "" or text.lower() in {"nan", "none", "null"}


def _cell_to_jsonable(value: Any) -> Any:
    if _is_blank(value):
        return None
    if isinstance(value, (int, float, str, bool)):
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return None
        return value
    return str(value)


@dataclass
class PreparedImport:
    source: CsvSource
    file_hash: str
    rows: list[ParsedRow] = field(default_factory=list)
