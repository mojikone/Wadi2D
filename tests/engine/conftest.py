"""Synthetic DEMs as real GeoTIFFs and small jobs that run through the whole pipeline."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import Affine

from wadi2d.config.schema import RunConfig

CRS = "EPSG:32640"
X0, Y0 = 400000.0, 2700000.0
NODATA = -9999.0


def write_dem(path: Path, z: np.ndarray, pixel: float, x0: float = X0, y0: float = Y0) -> Path:
    """Write ``z`` (rows south) as a float32 GeoTIFF; NaN becomes nodata."""
    ny, nx = z.shape
    with rasterio.open(
        path, "w", driver="GTiff", height=ny, width=nx, count=1, dtype="float32", nodata=NODATA, crs=CRS,
        transform=Affine(pixel, 0.0, x0, 0.0, -pixel, y0), tiled=True, blockxsize=32, blockysize=32,
    ) as dst:  # fmt: skip
        dst.write(np.nan_to_num(z, nan=NODATA).astype(np.float32), 1)
    return path


def tilted_box(nx: int, ny: int, pixel: float, slope: float, base: float = 100.0) -> np.ndarray:
    """A plane falling eastward; rows south."""
    xs = (np.arange(nx) + 0.5) * pixel
    return np.tile(base - slope * xs, (ny, 1))


def job(dem: Path, nx: int, ny: int, dx: float, **parts) -> RunConfig:
    """A job on a DEM written by ``write_dem``, with small outputs."""
    data = {
        "grid": {"dx": dx, "extent": (X0, Y0 - ny * dx, X0 + nx * dx, Y0)},
        "terrain": {"dem": str(dem)},
        "run": {"backend": "cpu"},
        "outputs": {"map_every_s": 0.0, "live_every_s": 0.0, "series_every_s": 5.0, "progress_every_s": 0.05},
    }
    for key, value in parts.items():
        data[key] = {**data.get(key, {}), **value} if isinstance(value, dict) else value
    return RunConfig.model_validate(data)


@pytest.fixture
def tilted_dem(tmp_path: Path) -> Path:
    """200 x 96 m at 2 m pixels, 1 % falling east."""
    return write_dem(tmp_path / "tilted.tif", tilted_box(100, 48, 2.0, 0.01), 2.0)
