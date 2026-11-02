"""Streams for the mesher: drainage area and how far a pixel lies below its surroundings.

WhiteboxTools does the hydrology, as in the owner's create_streams.py: breach depressions by least cost, then D8
accumulation. It runs on a coarsened copy of the DEM, once per mesh; nothing here reaches the solver.

Drainage area alone draws a stream across every plain. So a stream only counts where it is *incised*: below the mean of
the ground around it, measured over a square wide enough to reach past the banks. A mean over a square equals the centre
on any plane, so a stream on open sloping ground scores zero however steep the ground is.
"""

from __future__ import annotations

import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import Affine
from rasterio.windows import Window
from scipy import ndimage

NODATA = -9999.0
BREACH_DISTANCE_PIXELS = 40
"""Longest cut through a depression barrier, in analysis pixels."""
BIG_ELEVATION = 1e30
ANALYSIS_TRIES = 3
ANALYSIS_WAIT_S = 2.0
"""WhiteboxTools can exit 0 with nothing written; see _accumulate."""


@dataclass
class Terrain:
    """The analysis raster over a grid window, rows south from its north-west corner."""

    z: np.ndarray
    """Ground, m; NaN off the DEM."""
    area: np.ndarray
    """Drainage area, m2."""
    pixel: float


def read_coarse(
    path: str | Path, x0: float, y0: float, ny: int, nx: int, cell: float, factor: int
) -> np.ndarray:
    """Mean ground over ``factor`` x ``factor`` blocks of a ``cell``-sized lattice with origin (x0, y0)."""
    with rasterio.open(path) as src:
        t = src.transform
        step = cell / factor
        col = round((x0 - t.c) / t.a)
        row = round((t.f - y0) / -t.e)
        width = round(nx * cell / t.a)
        height = round(ny * cell / -t.e)
        window = Window(col, row, width, height)
        shape = (round(ny * cell / step), round(nx * cell / step))
        a = src.read(
            1, window=window, out_shape=shape, boundless=True, masked=True, resampling=Resampling.average
        )
    z = np.asarray(a.filled(np.nan), np.float64)
    return np.where(np.abs(z) > BIG_ELEVATION, np.nan, z)


def _accumulate(tool, tmp: Path) -> None:
    """z.tif to a.tif. WhiteboxTools keeps one settings file: two meshers at once can leave it exit 0 with nothing written."""
    code = 0
    for attempt in range(ANALYSIS_TRIES):
        if attempt:
            time.sleep(ANALYSIS_WAIT_S)
        code = tool.breach_depressions_least_cost(
            str(tmp / "z.tif"), str(tmp / "b.tif"), dist=BREACH_DISTANCE_PIXELS, fill=True
        )
        if code == 0:
            code = tool.d8_flow_accumulation(
                str(tmp / "b.tif"), str(tmp / "a.tif"), out_type="catchment area"
            )
        if code == 0 and (tmp / "a.tif").exists():
            return
    raise RuntimeError(
        f"the stream analysis wrote no result after {ANALYSIS_TRIES} tries (WhiteboxTools code {code}): "
        "if another mesh is being built, wait for it and run again"
    )


def drainage_area(z: np.ndarray, pixel: float, x0: float, y0: float, crs) -> np.ndarray:
    """D8 catchment area in m2 at every pixel of ``z``, through breached depressions."""
    try:
        import whitebox
    except ImportError as error:  # the mesher names what is missing, rather than failing inside a thread
        raise RuntimeError("mesh streams need the whitebox package") from error
    tool = whitebox.WhiteboxTools()
    tool.set_verbose_mode(False)
    profile = {
        "driver": "GTiff", "height": z.shape[0], "width": z.shape[1], "count": 1, "dtype": "float32",
        "nodata": NODATA, "crs": crs, "transform": Affine(pixel, 0.0, x0, 0.0, -pixel, y0),
    }  # fmt: skip
    with tempfile.TemporaryDirectory(prefix="wadi2d_mesh_") as folder:
        tmp = Path(folder)
        with rasterio.open(tmp / "z.tif", "w", **profile) as dst:
            dst.write(np.nan_to_num(z, nan=NODATA).astype(np.float32), 1)
        _accumulate(tool, tmp)
        with rasterio.open(tmp / "a.tif") as src:
            return np.maximum(src.read(1, masked=True).filled(0.0), 0.0).astype(np.float64)


def incision(z: np.ndarray, pixel: float, width: float) -> np.ndarray:
    """Mean ground over a ``width`` square, less the ground: positive in a channel, zero on a plane.

    Past the edge of the raster the ground continues by odd reflection, which keeps a plane a plane; a window of ours that
    reached nearest-value or mean filling would call the edge of any sloping raster a channel. A window that touches
    nodata says nothing, so it scores zero.
    """
    half = round(0.5 * width / pixel)
    valid = np.isfinite(z)
    filled = z
    if not valid.all():
        nearest = ndimage.distance_transform_edt(~valid, return_distances=False, return_indices=True)
        filled = z[tuple(nearest)]
    wide = np.pad(filled, half, mode="reflect", reflect_type="odd")
    mean = ndimage.uniform_filter(wide, 2 * half + 1, mode="nearest")[half:-half, half:-half]
    out = mean - filled
    if not valid.all():
        whole = ndimage.minimum_filter(valid.astype(np.uint8), 2 * half + 1, mode="nearest") > 0
        out = np.where(whole, out, 0.0)
    return out


def slope_change(z: np.ndarray, pixel: float, width: float) -> np.ndarray:
    """How far the ground leaves a plane over a ``width`` square, m; large at banks and slope breaks only."""
    return np.abs(incision(z, pixel, width))
