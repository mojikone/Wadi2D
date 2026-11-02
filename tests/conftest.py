"""Shared pytest fixtures and markers for Wadi2D.

Tests marked ``data`` need the Block 2 folder (read-only; path from ``WADI2D_BLOCK2`` or the default below).
Tests marked ``gpu`` need CuPy with a working device. Both are skipped, never failed, when absent.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

BLOCK2_DEFAULT = Path(r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2")


def _block2_path() -> Path:
    return Path(os.environ.get("WADI2D_BLOCK2", str(BLOCK2_DEFAULT)))


def _gpu_available() -> bool:
    try:
        import cupy as cp

        return bool(cp.cuda.Device(0).compute_capability)
    except Exception:
        return False


@pytest.fixture(scope="session")
def block2_dir() -> Path:
    """The Block 2 project folder; the test is skipped when it is not present. Never write into it."""
    p = _block2_path()
    if not p.is_dir():
        pytest.skip(f"Block 2 data folder not available at {p}")
    return p


@pytest.fixture(scope="session")
def hms_project_dir(block2_dir: Path) -> Path:
    p = block2_dir / "Hydrology" / "HEC_HMS_Block_02"
    if not p.is_dir():
        pytest.skip("HEC-HMS Block 2 project not present")
    return p


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    gpu_ok = _gpu_available()
    data_ok = _block2_path().is_dir()
    skip_gpu = pytest.mark.skip(reason="no NVIDIA GPU with CuPy available")
    skip_data = pytest.mark.skip(reason="Block 2 data folder not available")
    for item in items:
        if "gpu" in item.keywords and not gpu_ok:
            item.add_marker(skip_gpu)
        if "data" in item.keywords and not data_ok:
            item.add_marker(skip_data)
