@echo off
setlocal
cd /d "%~dp0"

where uv >nul 2>&1
if errorlevel 1 (
    echo uv was not found on PATH.
    echo Install it from https://docs.astral.sh/uv/ then try again.
    pause
    exit /b 1
)

echo Syncing dependencies...
uv sync
if errorlevel 1 (
    echo uv sync failed.
    pause
    exit /b 1
)

echo Starting Metric Atelier on http://127.0.0.1:8080
uv run metric-atelier %*
if errorlevel 1 pause
