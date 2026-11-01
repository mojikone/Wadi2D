"""RasterBed: a GeoTIFF as a ``BedSource``, read by windows so a 27 GB raster costs only what the grid touches.

A grid is pixel-aligned: its origin sits on DEM pixel corners and its cell size is a whole number of pixels. With
``pixel_stride`` s the bed sees one pixel in every s, without resampling the elevations, so a quick run skips I/O
and table work. Nodata becomes the nearest valid elevation inside a window; which cells are active is decided
once, by :meth:`RasterBed.active_mask`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.windows import Window
from scipy import ndimage

from wadi2d.io.identity import file_identity

ALIGN_TOLERANCE = 1e-6
"""Relative tolerance on 'a whole number of pixels'."""
HUGE_ELEVATION = 1e30
"""Anything above this is a nodata the file did not flag."""


@dataclass(frozen=True)
class GridWindow:
    """A pixel-aligned grid footprint; x0 is its west edge, y0 its north edge."""

    x0: float
    y0: float
    ny: int
    nx: int


class RasterBed:
    """Bed pixels from a north-up GeoTIFF. Call :meth:`bind` with the grid origin before :meth:`read`."""

    def __init__(self, path: str | Path, pixel_stride: int = 1) -> None:
        self.path = Path(path)
        self.stride = int(pixel_stride)
        self.src = rasterio.open(self.path)
        t = self.src.transform
        if t.b != 0.0 or t.d != 0.0 or t.e >= 0.0:
            raise ValueError(f"{self.path.name}: only north-up rasters are supported")
        if abs(t.a + t.e) > ALIGN_TOLERANCE * t.a:
            raise ValueError(f"{self.path.name}: pixels must be square, got {t.a} x {-t.e}")
        self.native = float(t.a)
        self.pixel = self.native * self.stride
        self.left = float(t.c)
        self.top = float(t.f)
        self.crs = self.src.crs
        self.row_origin = 0
        self.col_origin = 0

    def close(self) -> None:
        self.src.close()

    def __enter__(self) -> RasterBed:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def pixels_per_cell(self, dx: float) -> int:
        """Bed pixels along a cell; an error when ``dx`` is not a multiple of pixel * stride."""
        k = round(dx / self.pixel)
        if k < 1 or abs(k * self.pixel - dx) > ALIGN_TOLERANCE * dx:
            raise ValueError(
                f"cell size {dx} m is not a multiple of the DEM pixel {self.native} m x stride {self.stride}"
            )
        return k

    def snap(self, extent: tuple[float, float, float, float] | None, dx: float) -> GridWindow:
        """The aligned footprint that covers ``extent``, clipped to the raster; None takes the whole raster."""
        self.pixels_per_cell(dx)
        b = self.src.bounds
        xmin, ymin, xmax, ymax = extent if extent is not None else (b.left, b.bottom, b.right, b.top)
        xmin, ymin = max(xmin, b.left), max(ymin, b.bottom)
        xmax, ymax = min(xmax, b.right), min(ymax, b.top)
        if xmin >= xmax or ymin >= ymax:
            raise ValueError(f"extent {extent} does not meet the raster {tuple(b)}")
        col = int(np.floor((xmin - self.left) / self.native + ALIGN_TOLERANCE))
        row = int(np.floor((self.top - ymax) / self.native + ALIGN_TOLERANCE))
        x0 = self.left + col * self.native
        y0 = self.top - row * self.native
        nx = int(np.ceil((xmax - x0) / dx - ALIGN_TOLERANCE))
        ny = int(np.ceil((y0 - ymin) / dx - ALIGN_TOLERANCE))
        return GridWindow(x0, y0, ny, nx)

    def bind(self, x0: float, y0: float) -> None:
        """Set the grid origin; it must sit on a pixel corner."""
        col = (x0 - self.left) / self.native
        row = (self.top - y0) / self.native
        if abs(col - round(col)) > 1e-4 or abs(row - round(row)) > 1e-4:
            raise ValueError(f"grid origin ({x0}, {y0}) is not on a DEM pixel corner")
        self.col_origin = round(col)
        self.row_origin = round(row)

    def _window(self, row: int, col: int, nrows: int, ncols: int) -> np.ma.MaskedArray:
        """``nrows`` x ``ncols`` bed pixels from native (row, col); pixels off the raster come back masked."""
        s = self.stride
        skip_r = max(-(row // s), 0)
        skip_c = max(-(col // s), 0)
        nr = min(nrows - skip_r, (self.src.height - (row + skip_r * s)) // s)
        nc = min(ncols - skip_c, (self.src.width - (col + skip_c * s)) // s)
        out = np.ma.masked_all((nrows, ncols), np.float64)
        if nr <= 0 or nc <= 0:
            return out
        window = Window(col + skip_c * s, row + skip_r * s, nc * s, nr * s)
        a = self.src.read(1, window=window, out_shape=(nr, nc), masked=True, resampling=Resampling.nearest)
        values = np.asarray(a.filled(np.nan), dtype=np.float64)
        out[skip_r : skip_r + nr, skip_c : skip_c + nc] = np.ma.masked_invalid(
            np.where(values > HUGE_ELEVATION, np.nan, values)
        )
        return out

    def read(self, row0: int, col0: int, nrows: int, ncols: int) -> np.ndarray:
        """Bed pixels, float64, ``row0`` and ``col0`` counted in bed pixels from the grid origin."""
        a = self._window(
            self.row_origin + row0 * self.stride, self.col_origin + col0 * self.stride, nrows, ncols
        )
        mask = np.ma.getmaskarray(a)
        z = a.filled(0.0)
        if not mask.any() or mask.all():
            return z
        nearest = ndimage.distance_transform_edt(mask, return_distances=False, return_indices=True)
        return z[tuple(nearest)]

    def active_mask(self, w: GridWindow, dx: float) -> np.ndarray:
        """True on cells whose centre pixel holds data. One pixel per cell: fast, and enough for an edge."""
        k = self.pixels_per_cell(dx)
        self.bind(w.x0, w.y0)
        rows = self.row_origin + (np.arange(w.ny) * k + k // 2) * self.stride
        cols = self.col_origin + (np.arange(w.nx) * k + k // 2) * self.stride
        rkeep = (rows >= 0) & (rows < self.src.height)
        ckeep = (cols >= 0) & (cols < self.src.width)
        out = np.zeros((w.ny, w.nx), bool)
        if not rkeep.any() or not ckeep.any():
            return out
        step = k * self.stride
        shape = (int(rkeep.sum()), int(ckeep.sum()))
        r0 = max(int(rows[rkeep][0]) - step // 2, 0)
        c0 = max(int(cols[ckeep][0]) - step // 2, 0)
        height = min(shape[0] * step, self.src.height - r0)
        width = min(shape[1] * step, self.src.width - c0)
        # nearest through a decimated window: GDAL reads the blocks that hold the sampled pixels
        a = self.src.read(
            1,
            window=Window(c0, r0, width, height),
            out_shape=shape,
            masked=True,
            resampling=Resampling.nearest,
        )
        values = np.asarray(a.filled(np.nan), dtype=np.float64)
        out[np.ix_(rkeep, ckeep)] = np.isfinite(values) & (values < HUGE_ELEVATION)
        return out

    def identity(self, content_limit_mb: float) -> dict[str, object]:
        """What the grid cache hashes: the file as it stands."""
        return {
            "file": file_identity(self.path, content_limit_mb),
            "shape": [self.src.height, self.src.width],
            "transform": list(self.src.transform)[:6],
            "stride": self.stride,
        }
