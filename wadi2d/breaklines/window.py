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

__all__ = ["POINTER_STEPS", "Window", "flow_fields", "pixel_factor", "read_field", "read_window"]
from wadi2d.run import domain_mask, grid_window

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
        """``field`` at points of any shape (..., 2), bilinear by default; NaN off the raster and beside nodata.

        The field is read in place: a copy of it per call (the first version made one) cost 80 % of a suggestion on
        Bidah and hours on Block 2, where the bank search calls this thousands of times (found 2026-11-07).
        """
        r, c = self.rc(xy)
        out = ndimage.map_coordinates(field, [r.ravel(), c.ravel()], order=order, mode="constant", cval=np.nan)
        return out.reshape(r.shape)


def pixel_factor(dx: float, wanted: float) -> int:
    """Pixels per cell: the analysis pixel is the largest divisor of the cell not above the wanted pixel."""
    return max(1, int(np.floor(dx / wanted + 1e-9)))


def read_window(cfg: RunConfig, domain: np.ndarray | None = None, cache_dir: str | Path | None = None) -> Window:
    """The window's ground at the analysis pixel and the pixels under its active cells.

    ``domain`` is the job's domain mask when the caller has it (the grid build made it a moment before; read again
    here it was 44 s of Block 2's mesh, W92). The ground comes from the DEM's chunk store under ``cache_dir`` (the
    job's cache folder when None) as GDAL's own block average, on every core (``demstore.coarse``); without a store,
    through GDAL as before."""
    from wadi2d.demstore import cache_folder, open_bed
    from wadi2d.demstore.coarse import read_coarse_from

    factor = pixel_factor(cfg.grid.dx, cfg.mesh.analysis_pixel)
    with open_bed(cfg, cache_folder(cfg) if cache_dir is None else cache_dir) as bed:
        window = grid_window(cfg, bed)
        held = domain is not None and np.shape(domain) == (window.ny, window.nx)
        mask = np.asarray(domain, bool) if held else domain_mask(cfg, bed, window)
        crs = bed.crs.to_wkt() if bed.crs is not None else ""
        z = read_coarse_from(bed, cfg.terrain.dem, window.x0, window.y0, window.ny, window.nx, cfg.grid.dx, factor)
    inside = np.repeat(np.repeat(mask, factor, axis=0), factor, axis=1) if factor > 1 else mask.copy()
    return Window(z, inside & np.isfinite(z), window.x0, window.y0, cfg.grid.dx / factor, cfg.grid.dx, crs)


def read_field(win: Window, path: str | Path, fill: float = 0.0) -> np.ndarray:
    """Another raster on the same ground (a run's depth map) over the window, at the analysis pixel, by block mean;
    where it has no data, ``fill``."""
    factor = max(1, round(win.dx / win.pixel))
    ny, nx = win.z.shape[0] // factor, win.z.shape[1] // factor
    field = read_coarse(path, win.x0, win.y0, ny, nx, win.dx, factor)
    if field.shape != win.z.shape:
        raise ValueError(f"{path} does not cover the grid window as the DEM does ({field.shape} against {win.z.shape})")
    return np.where(np.isfinite(field), field, fill)


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
