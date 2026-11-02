"""GeoTIFF output: result maps (deflate, tiled) and the live raster, rewritten in place for the plugin."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import Affine

from wadi2d.grid.tiles import TileGrid

NODATA = -9999.0
BLOCK = 256
ZLEVEL = 4


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
) -> Path:
    """One float32 band, nodata where ``valid`` is False or the cell is outside the domain."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    keep = grid.mask if valid is None else (grid.mask & valid)
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
    }
    if min(ny, nx) >= BLOCK:
        profile.update(tiled=True, blockxsize=BLOCK, blockysize=BLOCK)
    with rasterio.open(out, "w", **profile) as dst:
        dst.write(band, 1)
        if tags:
            dst.update_tags(**tags)
    return out


def raster_profile(shape: tuple[int, int], pixel: float, x0: float, y0: float, crs) -> dict:
    """A compressed raster north-up from (x0, y0), for :func:`write_band`."""
    return {
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
    }


def write_band(path: str | Path, band: np.ndarray, profile: dict, nodata: float, tags=None) -> Path:
    """One band of any type; through a temporary name, so a stop never leaves half a file under the real name."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(f"{out.stem}.tmp{out.suffix}")
    with rasterio.open(tmp, "w", dtype=band.dtype.name, nodata=nodata, **profile) as dst:
        dst.write(band, 1)
        if tags:
            dst.update_tags(**tags)
    tmp.replace(out)
    return out


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
