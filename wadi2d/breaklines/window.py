"""The ground the suggestion reads: the job's grid window at the analysis pixel, with its D8 flow fields.

The same coarsened read as the mesher, so a wadi here is the wadi the mesher refines. WhiteboxTools gives the
pointer and the accumulation, as ``wadi2d.mesh.streams`` does for the area alone; the pointer is what lets a
thalweg be walked downstream pixel by pixel.
"""

from __future__ import annotations

import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import Affine
from scipy import ndimage

from wadi2d.config.schema import RunConfig
from wadi2d.mesh.streams import ANALYSIS_TRIES, ANALYSIS_WAIT_S, BREACH_DISTANCE_PIXELS, NODATA, read_coarse
from wadi2d.run import domain_mask, grid_window
from wadi2d.terrain import RasterBed

POINTER_STEPS = {
    1: (-1, 1),
    2: (0, 1),
    4: (1, 1),
    8: (1, 0),
    16: (1, -1),
    32: (0, -1),
    64: (-1, -1),
    128: (-1, 0),
}
"""WhiteboxTools D8 pointer codes to (row step, column step); 0 is no flow."""


@dataclass
class Window:
    """Ground over the grid window, rows south from (x0, y0), at ``pixel`` m."""

    z: np.ndarray
    """Mean ground per pixel, m; NaN off the DEM."""
    inside: np.ndarray
    """Pixels under active cells of the domain."""
    x0: float
    y0: float
    pixel: float
    dx: float
    crs: str
    """WKT of the DEM, or empty."""

    @property
    def transform(self) -> Affine:
        return Affine(self.pixel, 0.0, self.x0, 0.0, -self.pixel, self.y0)

    def xy(self, rows: np.ndarray, cols: np.ndarray) -> np.ndarray:
        """(n, 2) pixel centres."""
        return np.column_stack((self.x0 + (cols + 0.5) * self.pixel, self.y0 - (rows + 0.5) * self.pixel))

    def rc(self, xy: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Fractional (row, col) of points, for interpolation."""
        xy = np.asarray(xy, np.float64)
        return (self.y0 - xy[..., 1]) / self.pixel - 0.5, (xy[..., 0] - self.x0) / self.pixel - 0.5

    def sample(self, field: np.ndarray, xy: np.ndarray, order: int = 1) -> np.ndarray:
        """``field`` at points, bilinear by default; NaN off the raster."""
        r, c = self.rc(xy)
        filled = np.nan_to_num(field, nan=np.nan)
        return ndimage.map_coordinates(filled, [r, c], order=order, mode="constant", cval=np.nan)


def pixel_factor(dx: float, wanted: float) -> int:
    """Pixels per cell: the analysis pixel is the largest divisor of the cell not above the wanted pixel."""
    return max(1, int(np.floor(dx / wanted + 1e-9)))


def read_window(cfg: RunConfig) -> Window:
    with RasterBed(cfg.terrain.dem, cfg.terrain.pixel_stride) as bed:
        window = grid_window(cfg, bed)
        mask = domain_mask(cfg, bed, window)
        crs = bed.crs.to_wkt() if bed.crs is not None else ""
    factor = pixel_factor(cfg.grid.dx, cfg.mesh.analysis_pixel)
    z = read_coarse(cfg.terrain.dem, window.x0, window.y0, window.ny, window.nx, cfg.grid.dx, factor)
    inside = np.repeat(np.repeat(mask, factor, axis=0), factor, axis=1) if factor > 1 else mask.copy()
    return Window(z, inside & np.isfinite(z), window.x0, window.y0, cfg.grid.dx / factor, cfg.grid.dx, crs)


def flow_fields(win: Window) -> tuple[np.ndarray, np.ndarray]:
    """D8 drainage area, m2, and the D8 pointer of every pixel, through breached depressions.

    The retry is the mesher's: WhiteboxTools keeps one settings file, and two analyses at once can leave it exit 0
    with nothing written.
    """
    try:
        import whitebox
    except ImportError as error:
        raise RuntimeError("suggesting breaklines needs the whitebox package") from error
    tool = whitebox.WhiteboxTools()
    tool.set_verbose_mode(False)
    profile = {
        "driver": "GTiff", "height": win.z.shape[0], "width": win.z.shape[1], "count": 1, "dtype": "float32",
        "nodata": NODATA, "crs": win.crs or None, "transform": win.transform,
    }  # fmt: skip
    with tempfile.TemporaryDirectory(prefix="wadi2d_breaklines_") as folder:
        tmp = Path(folder)
        with rasterio.open(tmp / "z.tif", "w", **profile) as dst:
            dst.write(np.nan_to_num(win.z, nan=NODATA).astype(np.float32), 1)
        code = 0
        for attempt in range(ANALYSIS_TRIES):
            if attempt:
                time.sleep(ANALYSIS_WAIT_S)
            code = tool.breach_depressions_least_cost(
                str(tmp / "z.tif"), str(tmp / "b.tif"), dist=BREACH_DISTANCE_PIXELS, fill=True
            )
            if code == 0:
                code = tool.d8_pointer(str(tmp / "b.tif"), str(tmp / "p.tif"))
            if code == 0:
                code = tool.d8_flow_accumulation(
                    str(tmp / "p.tif"), str(tmp / "a.tif"), out_type="catchment area", pntr=True
                )
            if code == 0 and (tmp / "a.tif").exists() and (tmp / "p.tif").exists():
                break
        else:
            raise RuntimeError(
                f"the stream analysis wrote no result after {ANALYSIS_TRIES} tries (WhiteboxTools code {code}): "
                "a DEM with no CRS does this; otherwise, if a mesh is being built, wait for it and run again"
            )
        with rasterio.open(tmp / "a.tif") as src:
            area = np.maximum(src.read(1, masked=True).filled(0.0), 0.0).astype(np.float64)
        with rasterio.open(tmp / "p.tif") as src:
            pointer = src.read(1, masked=True).filled(0).astype(np.int32)
    return area, pointer
