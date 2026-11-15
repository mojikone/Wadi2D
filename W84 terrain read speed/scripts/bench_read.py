"""What limits a DEM window read: threads against processes, GDAL's block cache, the masked read, the overlap.

Args: mode(threads|procs) workers kind(raw|masked|bed|stored) pitch [cachemax]
``stored`` reads through the chunk store in the folder of the environment's W84_STORE (made on the first pass).
Windows of 1,857 pixels (a 20 m tile with the local radius's reach at 0.5 m) on a lattice of ``pitch`` pixels inside
Block 2's data; pitch 1280 is the table build's own overlap, 1857 none.
"""

import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

mode, workers, kind, pitch = sys.argv[1], int(sys.argv[2]), sys.argv[3], int(sys.argv[4])
if len(sys.argv) > 5:
    os.environ["GDAL_CACHEMAX"] = sys.argv[5]

import threading

import numpy as np
import rasterio
from rasterio.windows import Window

DEM = os.environ.get(
    "W84_DEM", r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology\Terrain\GGC_2_MERGE_HDSM.tif"
)
SIZE = 1857
N = int(os.environ.get("W84_N", "8"))  # N x N windows
COL0, ROW0 = int(os.environ.get("W84_COL0", "52000")), int(os.environ.get("W84_ROW0", "60000"))

local = threading.local()


def handle():
    src = getattr(local, "src", None)
    if src is None:
        src = local.src = rasterio.open(DEM)
    return src


def bed():
    b = getattr(local, "bed", None)
    if b is None:
        from wadi2d.terrain import RasterBed

        b = local.bed = RasterBed(DEM)
        if kind == "stored":
            from wadi2d.demstore import StoredBed, store_for

            b = local.bed = StoredBed(DEM, 1, store_for(DEM, b.src, os.environ["W84_STORE"], 64.0))
    return b


def one(i: int) -> float:
    r, c = ROW0 + (i // N) * pitch, COL0 + (i % N) * pitch
    if kind == "raw":
        a = handle().read(1, window=Window(c, r, SIZE, SIZE))
        return float(np.isfinite(a).mean())
    if kind == "masked":
        a = handle().read(1, window=Window(c, r, SIZE, SIZE), masked=True)
        return float(a.count()) / a.size
    z = bed().read(r, c, SIZE, SIZE)
    return float(np.isfinite(z).mean())


if __name__ == "__main__":
    items = list(range(N * N))
    pool = (ThreadPoolExecutor if mode == "threads" else ProcessPoolExecutor)(workers)
    with pool:
        list(pool.map(one, range(workers)))  # handles open, processes started
        if kind == "stored":
            list(pool.map(one, items))  # the store made: what is timed is the read of a warm store
        t0 = time.perf_counter()
        out = list(pool.map(one, items))
        wall = time.perf_counter() - t0
    print(
        f"{mode:7s} w={workers:2d} {kind:6s} pitch={pitch} cache={os.environ.get('GDAL_CACHEMAX', 'default')}: "
        f"{wall:6.2f} s, {1000 * wall / len(items):6.1f} ms a window, check {np.mean(out):.3f}"
    )
