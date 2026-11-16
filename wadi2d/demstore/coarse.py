"""GDAL's block average of the DEM, from the chunk store (W92).

The centre generator and the breakline suggestion read their ground as the mean of every ``k`` x ``k`` block of DEM
pixels (``wadi2d.mesh.streams.read_coarse``: a masked read with ``Resampling.average``). On Block 2's window that read
is GDAL decoding the whole window on one core, 240 s (W84). Here the same means come from the store, on every core,
and they are GDAL's to the last bit (``tests/demstore/test_coarse.py``; W92 holds it to ``read_coarse`` on Block 2's
whole window).

GDAL's average (``gcore/overview.cpp``, ``GDALResampleChunk_AverageOrRMS_T``, 3.12) has two paths, and a mean at a
tie between two float32 values comes out of them differently:

- a chunk whose mask is all valid: every pixel times 1/(k k), summed along each row, the rows summed, then
  ``k k * (total / (k k))``;
- a chunk holding a masked pixel: the valid pixels summed along each row, the rows summed, divided by their count.

Which path a block takes is decided per chunk of GDAL's own (``GDALRasterBand::RasterIOResampled``): the output is cut
into chunks of at most 1024 x 1024 DEM pixels, each read with a margin, and a chunk takes the masked path when the
mask over its margin holds a masked pixel. That partition is reproduced here (``gdal_chunks``). It holds for a window
inside the raster; a window reaching past it goes through rasterio's boundless VRT, and is read by GDAL as before.
"""

from __future__ import annotations

import math
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from numba import njit

from wadi2d.demstore.bed import StoredBed

BAND_ROWS = 16
"""Output rows a thread averages at a time: 16 x 10 rows of DEM pixels across Block 2's window are 150 MB."""
WORKERS = max(1, min(16, os.cpu_count() or 1))
FULL_RES_CHUNK = 1024 * 1024
"""GDAL's limit on a chunk's DEM pixels in ``RasterIOResampled``."""


@njit(cache=True, nogil=True)
def _block_means(z, mask, k, plain, masked, count, r0):
    """Rows ``r0`` on of the two means of every block and its valid count, from ``z`` (float64) and ``mask`` (True
    where no data), each as GDAL forms it (the module's words), cast to float32."""
    nr = z.shape[0] // k
    nc = plain.shape[1]
    inv = 1.0 / (k * k)
    kk = float(k * k)
    for i in range(nr):
        for j in range(nc):
            total_a = 0.0
            total_b = 0.0
            weight_b = 0.0
            n = 0
            for a in range(k):
                r = i * k + a
                line_a = 0.0
                line_b = 0.0
                line_w = 0.0
                for b in range(k):
                    c = j * k + b
                    v = z[r, c]
                    line_a += v * inv
                    if not mask[r, c]:
                        line_b += v
                        line_w += 1.0
                        n += 1
                total_a += line_a
                total_b += line_b
                weight_b += line_w
            plain[r0 + i, j] = np.float64(np.float32(kk * (total_a / (float(k) * float(k)))))
            masked[r0 + i, j] = np.float64(np.float32(total_b / weight_b)) if n else np.nan
            count[r0 + i, j] = n


def gdal_chunks(row: int, col: int, height: int, width: int, out_rows: int, out_cols: int, raster: tuple[int, int]):
    """GDAL's destination chunks of a resampled read of (row, col, height, width) into ``out_rows`` x ``out_cols``:
    (dst row, dst col, rows, cols) and the DEM pixels each one's mask is read over, (row0, row1, col0, col1)."""
    ry, rx = height / out_rows, width / out_cols
    ny, nx = raster
    by, bx = out_rows, out_cols
    while True:
        fx = min(3 + int(bx * rx), nx)
        fy = min(3 + int(by * ry), ny)
        if (bx == 1 and by == 1) or fx * fy <= FULL_RES_CHUNK:
            break
        if bx > 1 and (fx > fy or by == 1):
            bx //= 2
        else:
            by //= 2
    out = []
    for dy in range(0, out_rows, by):
        cy = min(by, out_rows - dy)
        y0 = row + int(dy * ry)
        y1 = min(row + 1 + math.ceil((dy + cy) * ry), ny)
        for dx in range(0, out_cols, bx):
            cx = min(bx, out_cols - dx)
            x0 = col + int(dx * rx)
            x1 = min(col + 1 + math.ceil((dx + cx) * rx), nx)
            out.append(((dy, dx, cy, cx), (y0, y1, x0, x1)))
    return out


def can_average(bed, x0: float, y0: float, ny: int, nx: int, cell: float) -> bool:
    """Whether ``coarse_mean`` gives GDAL's numbers: a float32 raster on the store, read at full pixels, the window
    inside the raster."""
    if not (isinstance(bed, StoredBed) and bed.store is not None and bed.stride == 1 and bed.src.dtypes[0] == "float32"):
        return False
    row, col, height, width = _native(bed, x0, y0, ny, nx, cell)
    return row >= 0 and col >= 0 and row + height <= bed.src.height and col + width <= bed.src.width


def _native(bed, x0, y0, ny, nx, cell):
    t = bed.src.transform
    return round((t.f - y0) / -t.e), round((x0 - t.c) / t.a), round(ny * cell / -t.e), round(nx * cell / t.a)


def coarse_mean(bed: StoredBed, x0: float, y0: float, ny: int, nx: int, cell: float, factor: int, workers: int = WORKERS) -> np.ndarray:
    """``read_coarse(bed.path, x0, y0, ny, nx, cell, factor)`` from the store: the mean ground of every block of the
    ``cell`` lattice cut ``factor`` times each way, float64, NaN where a block holds no data."""
    row, col, height, width = _native(bed, x0, y0, ny, nx, cell)
    shape = (ny * factor, nx * factor)
    if height % shape[0] or width % shape[1] or height // shape[0] != width // shape[1]:
        raise ValueError("the analysis pixel is not a whole number of DEM pixels")
    k = height // shape[0]
    plain = np.empty(shape, np.float64)
    masked = np.empty(shape, np.float64)
    count = np.empty(shape, np.int32)

    def band(r0: int) -> None:
        rows = min(BAND_ROWS, shape[0] - r0)
        z, mask = bed._window(row + r0 * k, col, rows * k, width)
        _block_means(z, mask, k, plain, masked, count, r0)

    starts = range(0, shape[0], BAND_ROWS)
    if workers > 1 and len(starts) > 1:
        with ThreadPoolExecutor(workers) as pool:
            for _ in pool.map(band, starts):
                pass
    else:
        for r0 in starts:
            band(r0)
    full = k * k
    for (dy, dx, cy, cx), (y0r, y1r, x0r, x1r) in gdal_chunks(row, col, height, width, shape[0], shape[1], (bed.src.height, bed.src.width)):
        blocks = count[dy : dy + cy, dx : dx + cx]
        if (blocks == full).all() and _margin_valid(bed, (y0r, y1r, x0r, x1r), (row + dy * k, row + (dy + cy) * k, col + dx * k, col + (dx + cx) * k)):
            masked[dy : dy + cy, dx : dx + cx] = plain[dy : dy + cy, dx : dx + cx]
    return np.where(np.abs(masked) > 1e30, np.nan, masked)


def _margin_valid(bed, queried, inner) -> bool:
    """Whether every DEM pixel GDAL reads the mask over, outside the blocks themselves, holds data."""
    y0, y1, x0, x1 = queried
    a0, a1, b0, b1 = inner
    for r0, r1, c0, c1 in ((y0, a0, x0, x1), (a1, y1, x0, x1), (a0, a1, x0, b0), (a0, a1, b1, x1)):
        if r1 > r0 and c1 > c0:
            _z, mask = bed._window(r0, c0, r1 - r0, c1 - c0)
            if mask.any():
                return False
    return True


def read_coarse_from(bed, path: str | Path, x0: float, y0: float, ny: int, nx: int, cell: float, factor: int) -> np.ndarray:
    """The store's means when the bed can give them, GDAL's read otherwise."""
    if bed is not None and Path(bed.path) == Path(path) and can_average(bed, x0, y0, ny, nx, cell):
        return coarse_mean(bed, x0, y0, ny, nx, cell, factor)
    from wadi2d.mesh.streams import read_coarse

    return read_coarse(path, x0, y0, ny, nx, cell, factor)


__all__ = ["can_average", "coarse_mean", "gdal_chunks", "read_coarse_from"]
