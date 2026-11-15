"""What a store chunk costs to make: opening the raster, decoding 2,048 x 2,048 pixels with and without GDAL's mask,
writing it with and without a flush to disk, on 1 to 32 threads. Args: a scratch folder."""

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import Window

DEM = r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology\Terrain\GGC_2_MERGE_HDSM.tif"
CH = int(os.environ.get("W84_CHUNK", "2048"))
scratch = Path(sys.argv[1])
scratch.mkdir(parents=True, exist_ok=True)

t0 = time.perf_counter()
for _ in range(20):
    with rasterio.open(DEM) as src:
        pass
print(f"open and close: {1000 * (time.perf_counter() - t0) / 20:.2f} ms")
with rasterio.open(DEM) as src:
    print("mask flags", src.mask_flag_enums, "dtype", src.dtypes[0])


def chunk(i: int, mode: str) -> float:
    r, c = 20 + (i // 16) % 30, 52000 // CH + i % 16  # rows of chunks inside the block's data, taken in turn
    with rasterio.open(DEM) as src:
        if mode == "raw":
            a = src.read(1, window=Window(c * CH, r * CH, CH, CH))
            return float(a[0, 0])
        a = src.read(1, window=Window(c * CH, r * CH, CH, CH), masked=True).filled(np.nan)
    if mode == "masked":
        return float(a[0, 0])
    tmp = scratch / f"c_{r}_{c}.tmp"
    with open(tmp, "wb") as f:
        np.save(f, a)
        if mode == "sync":
            f.flush()
            os.fsync(f.fileno())
    os.replace(tmp, scratch / f"c_{r}_{c}.npy")
    return float(a[0, 0])


n = 0
for mode in ("raw", "masked", "write", "sync"):
    for workers in (1, 4, 8, 16, 32):
        items = range(n, n + 4 * workers)  # fresh chunks each time: nothing in GDAL's cache
        n += 4 * workers
        with ThreadPoolExecutor(workers) as pool:
            t0 = time.perf_counter()
            list(pool.map(lambda i: chunk(i, mode), items))
            wall = time.perf_counter() - t0
        print(
            f"{mode:6s} w={workers:2d}: {1000 * wall / len(items):6.1f} ms a chunk of {CH} px, "
            f"{CH * CH * len(items) / wall / 1e6:7.1f} M px/s"
        )
