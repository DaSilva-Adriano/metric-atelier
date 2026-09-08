"""NiceGUI application entry."""

from __future__ import annotations

from pathlib import Path

from fastapi import Request
from nicegui import app, ui

from metric_atelier.store import get_store, init_store, resolve_data_dir


def _register_pages() -> None:
    from metric_atelier.views import compare as _compare  # noqa: F401
    from metric_atelier.views import library as _library  # noqa: F401
    from metric_atelier.views import settings as _settings  # noqa: F401
    from metric_atelier.views import video as _video  # noqa: F401


def _register_api() -> None:
    @app.post("/api/reorder-videos")
    async def reorder_videos(request: Request) -> dict:
        body = await request.json()
        get_store().reorder_videos(body.get("ids") or [])
        return {"ok": True}

    @app.post("/api/reorder-runs")
    async def reorder_runs(request: Request) -> dict:
        body = await request.json()
        get_store().reorder_runs(body.get("ids") or [])
        return {"ok": True}


def launch(
    *,
    host: str = "127.0.0.1",
    port: int = 8080,
    data_dir: Path | None = None,
    show: bool = True,
) -> None:
    init_store(resolve_data_dir(data_dir))
    _register_pages()
    _register_api()
    ui.run(
        host=host,
        port=port,
        title="Metric Atelier",
        favicon="📐",
        reload=False,
        show=show,
        storage_secret="metric-atelier-local",
        binding_refresh_interval=0.1,
    )
