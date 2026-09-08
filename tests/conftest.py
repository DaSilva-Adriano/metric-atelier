from __future__ import annotations

from pathlib import Path

import pytest

from metric_atelier.store import Store


@pytest.fixture
def store(tmp_path: Path) -> Store:
    return Store(tmp_path / "data")


@pytest.fixture
def samples_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "samples"
