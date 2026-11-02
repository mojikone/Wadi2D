"""A catchment known without any delineation: two V valleys joining one, on a plane falling south.

Every pixel drains to the one outlet at the south end, so the raster's area is the answer at the outlet, and the ridge
between the two arms splits the area above the fork by symmetry. Along the valley the bed falls at BED_SLOPE; across it the
ground rises at SIDE_SLOPE.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import Affine

pytest.importorskip("whitebox")

PIXEL = 10.0
NY, NX = 300, 200
X0, Y0 = 500_000.0, 2_500_000.0
BED_SLOPE = 0.02
SIDE_SLOPE = 0.05
FORK_ROW = 150
"""The two arms join at this row; rows count from the north."""
ARM_OFFSET = 50
"""Columns between each arm and the main valley at the north edge; they close linearly to the fork."""
BED_NORTH = 100.0
CRS = "EPSG:32640"


def valley_dem() -> np.ndarray:
    """Ground, m."""
    rows, cols = np.mgrid[0:NY, 0:NX]
    distance_along = (NY - rows) * PIXEL * BED_SLOPE
    centre = NX // 2
    spread = ARM_OFFSET * np.maximum(FORK_ROW - rows, 0) / FORK_ROW
    across = np.minimum(np.abs(cols - (centre - spread)), np.abs(cols - (centre + spread))) * PIXEL
    return BED_NORTH + distance_along + across * SIDE_SLOPE


def straight_valley(flat_width: float = 0.0) -> np.ndarray:
    """One valley down the middle, ``flat_width`` of flat bed between banks at SIDE_SLOPE."""
    rows, cols = np.mgrid[0:NY, 0:NX]
    across = np.maximum(np.abs(cols - NX // 2) * PIXEL - 0.5 * flat_width, 0.0)
    return BED_NORTH + (NY - rows) * PIXEL * BED_SLOPE + across * SIDE_SLOPE


def write_raster(path: Path, values: np.ndarray, nodata: float = -9999.0) -> Path:
    """A GeoTIFF on the test lattice."""
    with rasterio.open(
        path, "w", driver="GTiff", height=values.shape[0], width=values.shape[1], count=1, dtype="float32",
        nodata=nodata, crs=CRS, transform=Affine(PIXEL, 0.0, X0, 0.0, -PIXEL, Y0),
    ) as dst:  # fmt: skip
        dst.write(values.astype(np.float32), 1)
    return path


def row_y(row: int) -> float:
    """Northing of a row's centre."""
    return Y0 - (row + 0.5) * PIXEL


def col_x(col: int) -> float:
    """Easting of a column's centre."""
    return X0 + (col + 0.5) * PIXEL


@dataclass
class Valley:
    """The files of the synthetic catchment."""

    folder: Path
    dem: Path
    job: Path


def write_job(folder: Path, dem: Path, **parts) -> Path:
    """A job on the DEM, cell size one pixel."""
    extent = [X0, Y0 - NY * PIXEL, X0 + NX * PIXEL, Y0]
    job = {
        "grid": {"dx": PIXEL, "extent": extent},
        "mesh": {"analysis_pixel": PIXEL},
        "terrain": {"dem": str(dem)},
    }
    for key, value in parts.items():
        job[key] = {**job.get(key, {}), **value}
    path = folder / "job.json"
    path.write_text(json.dumps(job), encoding="utf-8")
    return path


@pytest.fixture
def valley(tmp_path: Path) -> Valley:
    dem = write_raster(tmp_path / "dem.tif", valley_dem())
    return Valley(tmp_path, dem, write_job(tmp_path, dem))
