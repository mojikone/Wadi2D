"""The analysis raster of a basin: ground, breached ground and the D8 lines, over the job's window and domain.

WhiteboxTools does the hydrology through the mesher's own calls (:mod:`wadi2d.mesh.streams`): breach depressions by least
cost, then D8. Its pointer raster becomes flat receiver indices, so everything after this module is plain arrays. Nothing
here reaches the solver, and the job's DEM file is only read.

Interface: :class:`Surface`, :func:`analysis_pixel`, :func:`read_surface`, :func:`flow_surface`.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

import numpy as np
import rasterio
import shapely
from rasterio import features
from rasterio.transform import Affine
from rasterio.windows import from_bounds

from wadi2d.basin.kernels import NONE, accumulate, upstream_first
from wadi2d.config.schema import BasinSettings, RunConfig
from wadi2d.mesh.streams import NODATA, _accumulate, read_coarse
from wadi2d.terrain.vector import read_features

M2_PER_KM2 = 1.0e6
POINTER_CODES = {
    1: (-1, 1),
    2: (0, 1),
    4: (1, 1),
    8: (1, 0),
    16: (1, -1),
    32: (0, -1),
    64: (-1, -1),
    128: (-1, 0),
}
"""WhiteboxTools' D8 pointer: code to (row, column) step."""


@dataclass
class Surface:
    """Everything the delineation reads, rows south from the north-west corner at (x0, y0)."""

    z: np.ndarray
    """Ground, m; NaN off the DEM and off the domain."""
    breached: np.ndarray
    """Ground after breaching, falling along every D8 line, m."""
    down: np.ndarray
    """Receiver of each flat pixel, NONE at an outlet and off the ground."""
    order: np.ndarray
    """Flat pixels, upstream first."""
    count: np.ndarray
    """Pixels draining through each flat pixel, itself included."""
    pixel: float
    x0: float
    y0: float
    crs: str

    @property
    def shape(self) -> tuple[int, int]:
        """Rows, columns."""
        return self.z.shape

    @property
    def nx(self) -> int:
        """Columns."""
        return self.z.shape[1]

    @property
    def transform(self) -> Affine:
        """Pixel to map."""
        return Affine(self.pixel, 0.0, self.x0, 0.0, -self.pixel, self.y0)

    @property
    def km2_per_pixel(self) -> float:
        """The area of one pixel."""
        return self.pixel * self.pixel / M2_PER_KM2

    @cached_property
    def valid(self) -> np.ndarray:
        """Flat pixels with ground."""
        return np.isfinite(self.z).ravel()

    def xy(self, flat: np.ndarray | int) -> tuple[np.ndarray, np.ndarray]:
        """Map coordinates of pixel centres."""
        row, col = np.divmod(np.asarray(flat, dtype=np.int64), self.nx)
        return self.x0 + (col + 0.5) * self.pixel, self.y0 - (row + 0.5) * self.pixel

    def flat(self, x: float, y: float) -> int:
        """The pixel under a map point, NONE outside the raster."""
        col = int(np.floor((x - self.x0) / self.pixel))
        row = int(np.floor((self.y0 - y) / self.pixel))
        if 0 <= row < self.shape[0] and 0 <= col < self.nx:
            return row * self.nx + col
        return NONE

    def line_pixels(self, coordinates: list[tuple[float, float]]) -> np.ndarray:
        """Flat pixels on ground that a polyline touches; a D8 line cannot slip between them."""
        ny, nx = self.shape
        xmin, ymin, xmax, ymax = shapely.LineString(coordinates).bounds
        col0 = max(int(np.floor((xmin - self.x0) / self.pixel)), 0)
        row0 = max(int(np.floor((self.y0 - ymax) / self.pixel)), 0)
        col1 = min(int(np.floor((xmax - self.x0) / self.pixel)) + 1, nx)
        row1 = min(int(np.floor((self.y0 - ymin) / self.pixel)) + 1, ny)
        if col1 <= col0 or row1 <= row0:
            return np.empty(0, dtype=np.int64)
        burned = features.rasterize(
            [shapely.LineString(coordinates)],
            out_shape=(row1 - row0, col1 - col0),
            transform=self.transform * Affine.translation(col0, row0),
            all_touched=True,
            dtype=np.uint8,
        )
        rows, cols = np.nonzero(burned)
        flat = (rows + row0) * nx + cols + col0
        return flat[self.valid[flat]]


def analysis_pixel(cfg: RunConfig, settings: BasinSettings) -> float:
    """The pixel of the delineation: the setting, else the mesher's."""
    return cfg.mesh.analysis_pixel if settings.analysis_pixel is None else settings.analysis_pixel


def _window(cfg: RunConfig, polygon: shapely.Geometry | None, pixel: float) -> tuple[float, float, int, int]:
    """West edge, north edge, rows, columns of the analysis raster: DEM pixel corners round the domain."""
    with rasterio.open(cfg.terrain.dem) as src:
        t, b = src.transform, src.bounds
    extent = polygon.bounds if polygon is not None else cfg.grid.extent
    if extent is None:
        extent = (b.left, b.bottom, b.right, b.top)
    xmin, ymin = max(extent[0], b.left), max(extent[1], b.bottom)
    xmax, ymax = min(extent[2], b.right), min(extent[3], b.top)
    if xmin >= xmax or ymin >= ymax:
        raise ValueError(f"the job's area {extent} does not meet the DEM {tuple(b)}")
    window = from_bounds(xmin, ymin, xmax, ymax, t).round_offsets(op="floor")
    x0, y0 = t * (window.col_off, window.row_off)
    return (
        x0,
        y0,
        int(np.ceil((y0 - ymin) / pixel)),
        int(np.ceil((xmax - x0) / pixel)),
    )


def _on_domain(
    z: np.ndarray, polygon: shapely.Geometry | None, x0: float, y0: float, pixel: float
) -> np.ndarray:
    """Ground with everything off the domain gone."""
    if polygon is None:
        return z
    inside = features.geometry_mask(
        [polygon], out_shape=z.shape, transform=Affine(pixel, 0.0, x0, 0.0, -pixel, y0), invert=True
    )
    return np.where(inside, z, np.nan)


def read_surface(cfg: RunConfig, settings: BasinSettings) -> tuple[np.ndarray, float, float, float, str]:
    """Ground on the analysis raster, its pixel, west edge and north edge, and its CRS."""
    if cfg.terrain.dem is None:
        raise ValueError("a basin needs terrain.dem")
    pixel = analysis_pixel(cfg, settings)
    with rasterio.open(cfg.terrain.dem) as src:
        crs = src.crs.to_wkt() if src.crs is not None else ""
    polygon = None
    if cfg.grid.domain is not None:
        polygon = shapely.union_all([shape for _props, shape in read_features(cfg.grid.domain, crs)])
    x0, y0, ny, nx = _window(cfg, polygon, pixel)
    if ny * nx > settings.max_pixels:
        raise ValueError(
            f"the delineation would take {ny * nx:,} pixels of {pixel} m, above max_pixels "
            f"{settings.max_pixels:,}: use a coarser analysis pixel"
        )
    z = _on_domain(read_coarse(cfg.terrain.dem, x0, y0, ny, nx, pixel, 1), polygon, x0, y0, pixel)
    if not np.isfinite(z).any():
        raise ValueError("no ground under the job's domain")
    return z, pixel, x0, y0, crs


def _receivers(pointer: np.ndarray) -> np.ndarray:
    """Flat receivers from WhiteboxTools' pointer codes."""
    ny, nx = pointer.shape
    down = np.full(pointer.size, NONE, dtype=np.int64)
    for code, (row_step, col_step) in POINTER_CODES.items():
        rows, cols = np.nonzero(pointer == code)
        inside = (
            (rows + row_step >= 0) & (rows + row_step < ny) & (cols + col_step >= 0) & (cols + col_step < nx)
        )
        rows, cols = rows[inside], cols[inside]
        down[rows * nx + cols] = (rows + row_step) * nx + cols + col_step
    return down


def _whitebox(z: np.ndarray, pixel: float, x0: float, y0: float, crs: str) -> tuple[np.ndarray, np.ndarray]:
    """Breached ground and the D8 pointer."""
    try:
        import whitebox
    except ImportError as error:
        raise RuntimeError("a basin needs the whitebox package") from error
    tool = whitebox.WhiteboxTools()
    tool.set_verbose_mode(False)
    profile = {
        "driver": "GTiff", "height": z.shape[0], "width": z.shape[1], "count": 1, "dtype": "float32",
        "nodata": NODATA, "crs": crs or None, "transform": Affine(pixel, 0.0, x0, 0.0, -pixel, y0),
    }  # fmt: skip
    with tempfile.TemporaryDirectory(prefix="wadi2d_basin_") as folder:
        tmp = Path(folder)
        with rasterio.open(tmp / "z.tif", "w", **profile) as dst:
            dst.write(np.nan_to_num(z, nan=NODATA).astype(np.float32), 1)
        _accumulate(tool, tmp)
        code = tool.d8_pointer(str(tmp / "b.tif"), str(tmp / "p.tif"))
        if code != 0 or not (tmp / "p.tif").exists():
            raise RuntimeError(f"WhiteboxTools wrote no D8 pointer (code {code})")
        with rasterio.open(tmp / "b.tif") as src:
            breached = src.read(1, masked=True).filled(np.nan).astype(np.float64)
        with rasterio.open(tmp / "p.tif") as src:
            pointer = src.read(1, masked=True).filled(0).astype(np.int64)
    return breached, pointer


def flow_surface(z: np.ndarray, pixel: float, x0: float, y0: float, crs: str) -> Surface:
    """Run the hydrology over ``z``."""
    breached, pointer = _whitebox(z, pixel, x0, y0, crs)
    pointer = np.where(np.isfinite(z), pointer, 0)
    down = _receivers(pointer)
    order = upstream_first(down)
    if order.size != down.size:
        raise RuntimeError(f"the D8 lines hold a cycle: {down.size - order.size} pixels never drain")
    valid = np.isfinite(z).ravel()
    return Surface(z, breached, down, order, accumulate(down, order, valid), pixel, x0, y0, crs)
