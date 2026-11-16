"""GeoTIFF output: result maps (deflate, tiled) and the live raster, rewritten in place for the plugin."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import Affine
from rasterio.windows import Window

from wadi2d.grid.tiles import TileGrid

NODATA = -9999.0
BLOCK = 256
ZLEVEL = 4
THREADS = "ALL_CPUS"
"""GDAL compresses a GeoTIFF's blocks on every core: a 0.7 GB band of Block 2 in 7.6 s against 56.5 on one (W50)."""


def grid_transform(grid: TileGrid, stride: int = 1) -> Affine:
    """West-north origin, rows south."""
    return Affine(grid.dx * stride, 0.0, grid.x0, 0.0, -grid.dx * stride, grid.y0)


def write_map(
    path: str | Path,
    data: np.ndarray,
    grid: TileGrid,
    crs,
    valid: np.ndarray | None = None,
    tags: dict[str, str] | None = None,
    also: np.ndarray | None = None,
) -> Path:
    """One float32 band, nodata where ``valid`` is False or the cell is outside the domain. ``also`` marks cells
    outside the lattice's own mask that hold a value all the same: the squares an aligned strip replaced (W86)."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    inside = grid.mask if also is None else (grid.mask | also)
    keep = inside if valid is None else (inside & valid)
    band = np.where(keep, data, NODATA).astype(np.float32)
    ny, nx = band.shape
    profile = {
        "driver": "GTiff",
        "height": ny,
        "width": nx,
        "count": 1,
        "dtype": "float32",
        "nodata": NODATA,
        "crs": crs,
        "transform": grid_transform(grid),
        "compress": "deflate",
        "zlevel": ZLEVEL,
        "predictor": 2,
        "num_threads": THREADS,
    }
    if min(ny, nx) >= BLOCK:
        profile.update(tiled=True, blockxsize=BLOCK, blockysize=BLOCK)
    with rasterio.open(out, "w", **profile) as dst:
        dst.write(band, 1)
        if tags:
            dst.update_tags(**tags)
    return out


def raster_profile(shape: tuple[int, int], pixel: float, x0: float, y0: float, crs) -> dict:
    """A compressed raster north-up from (x0, y0), for :func:`write_band` and :class:`BandWriter`. Sparse: a block
    that holds nothing but nodata takes no room in the file and reads back as nodata (W50)."""
    return {
        "sparse_ok": True,
        "driver": "GTiff",
        "height": shape[0],
        "width": shape[1],
        "count": 1,
        "crs": crs,
        "transform": Affine(pixel, 0.0, x0, 0.0, -pixel, y0),
        "compress": "deflate",
        "zlevel": ZLEVEL,
        "tiled": True,
        "blockxsize": BLOCK,
        "blockysize": BLOCK,
        "BIGTIFF": "IF_SAFER",
        "num_threads": THREADS,
    }


LOSSY = "LERC_DEFLATE"
"""The compression of a float raster of record with a bounded error (W100): LERC keeps every value within the error
asked for and the nodata exactly, DEFLATE packs what LERC leaves; read by any GDAL from 2.4, QGIS's included."""
OVERVIEW_SMALLEST = BLOCK
"""Reduced copies are halved until the longer side is under this many pixels."""


def float_record(profile: dict, max_error: float) -> dict:
    """``profile`` for a float raster of record: LERC within ``max_error``, or with 0 every digit kept, DEFLATE with
    the floating-point predictor. Block 2's depth at 0.5 m: 3.4 GB in plain DEFLATE (W100 measures the rest)."""
    out = {key: value for key, value in profile.items() if key not in ("compress", "zlevel", "predictor")}
    if max_error > 0.0:
        return {**out, "compress": LOSSY, "max_z_error": float(max_error)}
    return {**out, "compress": "deflate", "zlevel": ZLEVEL, "predictor": 3}


def overview_levels(shape: tuple[int, int]) -> list[int]:
    """Factors 2, 4, 8, ... until the reduced raster's longer side is under :data:`OVERVIEW_SMALLEST`."""
    levels, factor = [], 2
    while max(shape) / (factor // 2) > OVERVIEW_SMALLEST:
        levels.append(factor)
        factor *= 2
    return levels


def _build_overviews(dst, resampling) -> None:
    """Reduced copies inside the file, on every core: a map seen whole then reads a few blocks (W100: Block 2's
    rasters had none, so QGIS read 9.1 G pixels at every zoom)."""
    from rasterio.enums import Resampling

    levels = overview_levels((dst.height, dst.width))
    if levels:
        with rasterio.Env(GDAL_NUM_THREADS=THREADS):
            dst.build_overviews(levels, getattr(Resampling, resampling))
        dst.update_tags(ns="rio_overview", resampling=resampling)


def write_band(
    path: str | Path, band: np.ndarray, profile: dict, nodata: float, tags=None, overviews: str | None = None
) -> Path:
    """One band of any type; through a temporary name, so a stop never leaves half a file under the real name.
    ``overviews`` names the resampling of its reduced copies (``average``, ``mode``), None for none."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(f"{out.stem}.tmp{out.suffix}")
    with rasterio.open(tmp, "w", dtype=band.dtype.name, nodata=nodata, **profile) as dst:
        dst.write(band, 1)
        if tags:
            dst.update_tags(**tags)
        if overviews is not None:
            _build_overviews(dst, overviews)
    tmp.replace(out)
    return out


class BandWriter:
    """One band written window by window, each window on the block lattice; what no window covers is nodata.

    A flood on a 0.5 m raster wets a twentieth of its bounding box: written whole, Block 2's band is 17 GB in memory
    and its empty blocks are most of the file (W50). Through a temporary name, as :func:`write_band`; leaving the
    ``with`` on an error removes it. ``overviews`` as :func:`write_band`, built once every window is written.
    """

    def __init__(self, path: str | Path, profile: dict, dtype, nodata: float, tags=None, overviews: str | None = None) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.tmp = self.path.with_name(f"{self.path.stem}.tmp{self.path.suffix}")
        self.tags = tags
        self.overviews = overviews
        self.dst = rasterio.open(self.tmp, "w", dtype=np.dtype(dtype).name, nodata=nodata, **profile)

    def write(self, tile: np.ndarray, row: int, col: int) -> None:
        self.dst.write(tile, 1, window=Window(col, row, tile.shape[1], tile.shape[0]))

    def __enter__(self) -> BandWriter:
        return self

    def __exit__(self, kind, *_exc: object) -> None:
        if kind is None and self.tags:
            self.dst.update_tags(**self.tags)
        try:
            if kind is None and self.overviews is not None:
                _build_overviews(self.dst, self.overviews)
        except BaseException:
            self.dst.close()
            self.tmp.unlink(missing_ok=True)
            raise
        self.dst.close()
        if kind is None:
            self.tmp.replace(self.path)
        else:
            self.tmp.unlink(missing_ok=True)


class LiveRaster:
    """Uncompressed float32 band overwritten in place, ``stride`` cells per pixel, mean over the cells."""

    def __init__(self, path: str | Path, grid: TileGrid, crs, stride: int) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.stride = stride
        self.mask = self._coarsen(grid.mask.astype(np.float32)) > 0.0
        ny, nx = self.mask.shape
        with rasterio.open(
            self.path, "w", driver="GTiff", height=ny, width=nx, count=1, dtype="float32", nodata=NODATA,
            crs=crs, transform=grid_transform(grid, stride),
        ) as dst:  # fmt: skip
            dst.write(np.full((ny, nx), NODATA, np.float32), 1)

    def _coarsen(self, a: np.ndarray) -> np.ndarray:
        s = self.stride
        ny, nx = a.shape[0] // s, a.shape[1] // s
        return a[: ny * s, : nx * s].reshape(ny, s, nx, s).mean(axis=(1, 3))

    def write(self, depth: np.ndarray) -> bool:
        """Rewrite the band; False when a reader holds the file, and the next frame will do."""
        band = np.where(self.mask, self._coarsen(depth), NODATA).astype(np.float32)
        try:
            with rasterio.open(self.path, "r+") as dst:
                dst.write(band, 1)
        except rasterio.errors.RasterioIOError:
            return False
        return True
