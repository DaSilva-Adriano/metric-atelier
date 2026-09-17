# Metric Atelier

A local Python app for importing, grouping, annotating, filtering, and comparing video quality metric CSVs (PSNR / SSIM / MS-SSIM / VMAF / LPIPS / ERQA). Charts and tables are meant to drop straight into a bachelor thesis or a report.

No login, no cloud, no telemetry. Bound to `127.0.0.1` by default. Original CSV files are **never rewritten**.

## Install and run

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12+.

Double-click `start.bat`, or from a terminal:

```bash
uv sync
uv run metric-atelier
```

Then open http://127.0.0.1:8080 if the browser does not open on its own.

Useful flags:

```bash
uv run metric-atelier --port 8080
uv run metric-atelier --data-dir D:\metrics\atelier
uv run metric-atelier --no-browser
```

Data directory (override with `--data-dir` or `METRIC_ATELIER_HOME`):

| Path | What |
| --- | --- |
| `data/atelier.sqlite` | Names, notes, tags, hidden flags, order, chart settings, colors |
| `data/imports/` | Read-only snapshots of imported CSVs |
| `data/exports/` | PNG / SVG / PDF figures and table exports |

Raw metric values live in the database as imported snapshots. Editing a friendly name or hiding a row never touches the file on disk.

## Quick start with the samples

Empty library → **Load sample datasets**, or import `samples/beauty.csv` and `samples/kartingtime.csv`.

You should get two videos:

- **Beauty** — 360p / 480p / 1080p / 2160p × bicubic / lanczos / vsr, including a broken 1080p VSR row and a resolution-mismatch error row
- **Karting Time** — 360p / 720p / 1080p × bicubic / lanczos / vsr, parsed from long `s-KartingTime_3840x2160_…` names

A later CSV whose `distorted` names still start with `beauty` attaches to Beauty, not a second card.

## How grouping works

Every CSV row is an immutable **Run**. User metadata (name, notes, hidden, order, color) is a separate annotation layer.

`video_id` is a slug of the **content title only** — not resolution, not method:

| Filename | Title | `video_id` |
| --- | --- | --- |
| `v-beauty-360p-24fps-bicubic` | Beauty | `beauty` |
| `v-beauty-1080p-24fps-vsr` | Beauty | `beauty` |
| `s-KartingTime_3840x2160_60fps_yuv444_16bits_70-720p-60fps-vsr` | Karting Time | `kartingtime` |

The parser does not assume a single pattern:

- **Pattern A** — prefix + CamelCase title + source `WxH` / fps / yuv / bits + target `720p-60fps-vsr`
- **Pattern B** — `v-beauty-360p-24fps-bicubic`
- Known methods include bicubic, lanczos, vsr, **ANIMEJANAI_BAL**, **FSRCNNX8**, **FSRCNNX16**, …
- A registered name with `_` (ANIMEJANAI_BAL) is the full display name. An extra unregistered tail (`ANIMEJANAI_BAL_V3`) is hidden unless Settings → Display → **Show full method names** is on. Unregistered `xxxxx_yyyyy` uses the first part as the label unless that toggle is on.
- Unknown methods stay as the raw token (`splatting`, …)
- Names that have no title land in **Unassigned** so you can move them
- JSON export `name` / `method` follow the current display name (`method_key` is the canonical id)

Re-import of the same file is deduplicated (`run_id` = hash of file content + row index + distorted name). Settings → Import chooses **skip** or **refresh metrics** (notes, names, hidden, and order are never clobbered).

## Hide vs delete

**Hide** is the first-class action for junk (wrong resolution, failed VSR, aborted encode, collapsed PSNR). Hidden runs:

- disappear from the default table and from charts
- remain listed under **Hidden (n)** and can be restored
- never modify the source CSV
- are excluded from exported figures unless **Include hidden in charts** is on

Filter chips for method / resolution are view state only.

**Delete a video** from the library card (trash icon) or the video page. That removes the source and all of its runs from Metric Atelier.

**Delete a row** in editing mode (not Presentation): select rows → **Delete selected**, or open a row and **Delete row**. Metric numbers cannot be edited — imported values stay as imported.

Original CSVs are never rewritten. Soft-delete (Settings → Data) still exists for imported-file cleanup with undo.

## Keyboard

| Key | Action |
| --- | --- |
| `/` | Focus search |
| `i` | Import |
| `h` | Hide selected runs |
| `p` | Presentation mode (hides edit chrome, larger type) |
| `?` | Shortcut list |
| `1` `2` `3` | Library / Compare / Settings |

## Screenshot tips for thesis figures

1. Open the video, hide the broken rows, sort by resolution.
2. Turn on **Presentation**.
3. Pick a chart type: small multiples (default), grouped bar, slope, delta, ranked bars, horizontal bars, heatmap, scatter, or radar.
4. Use **Metric** to show **All metrics** (one panel per metric, the default) or a single one (VMAF, PSNR-Y, SSIM, …). The same control applies to every chart type, including those that used to plot only VMAF.
5. Set **Order** so categories or bars follow resolution, method, value (low→high or high→low), or the table’s custom order. Method order and resolution order live under Settings → Display.
6. Optional: Settings → Charts → **Metric thresholds** (VMAF, PSNR, …). Comma-separated values (e.g. `80, 90, 95`) each become a dotted reference line. Cells that miss every line are flagged. ↑ metrics fail below the lowest line; ↓ metrics fail above the highest.
7. Edit the chart title (`Beauty — 24 fps, upscaling to 4K`).
8. Export **PNG 2×** (about 2000 px wide, white background), SVG / PDF, or **Export JSON**.
9. Tables use tabular lining figures and never dump raw 15-decimal floats (VMAF 1 dp, PSNR 2, SSIM / LPIPS / ERQA 3).

**Compare** (nav item 2) takes two or more contents. Series align on method + resolution. The same All / specific metric control applies. **Export JSON** writes the aligned comparison (`kind: metric-atelier-comparison`) with each content’s metric values per combo.

Direction is labeled on every column and axis (`↑` higher is better, `↓` lower is better). LPIPS is lower-is-better; ERQA is higher-is-better (1.0 is perfect restoration).

Figure export uses Plotly + Kaleido. Kaleido 1.x needs a local Chrome/Chromium. If PNG/PDF fails, an HTML fallback is written next to the export and the UI says so.

## Tests and lint

```bash
uv run pytest
uv run ruff check src tests
uv run ruff format src tests
```

## Portable annotations and dataset JSON

Settings → Data → **Export annotations JSON** saves names, notes, tags, hidden flags, order, and chart settings. Re-import it after loading the same CSVs on another machine.

**Export JSON** on a video (or Settings → Data → **Export dataset JSON**) writes a dataset file where `method` (`vsr`, `bicubic`, …) and `resolution` (`720p`, `1080p`, …) are first-class fields, along with metric values. Do not parse those out of `raw_name` — the filename is only a label.

## License

Metric Atelier is free software under the [GNU General Public License v3.0 or later](LICENSE).
