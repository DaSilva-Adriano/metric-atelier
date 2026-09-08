"""Console script: metric-atelier."""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="metric-atelier",
        description="Local web app for comparing video quality metric CSVs.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8080, help="Port (default 8080)")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="User data directory (default ./data, or METRIC_ATELIER_HOME)",
    )
    parser.add_argument("--no-browser", action="store_true", help="Do not open a browser window")
    args = parser.parse_args()
    from metric_atelier.app import launch

    launch(host=args.host, port=args.port, data_dir=args.data_dir, show=not args.no_browser)


if __name__ == "__main__":
    main()
