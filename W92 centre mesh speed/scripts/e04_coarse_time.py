"""Where the store's block average spends its time on a job's window: the bands' pixels, the kernel, GDAL's chunks.

    python e04_coarse_time.py <job.json> [workers]
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from s01_mesh import cache_folder

import wadi2d.demstore.coarse as c
from wadi2d.breaklines.window import pixel_factor
from wadi2d.demstore import open_bed
from wadi2d.run import grid_window, load_job

cfg = load_job(Path(sys.argv[1]))
workers = int(sys.argv[2]) if len(sys.argv) > 2 else c.WORKERS
spent = {"pixels": 0.0, "kernel": 0.0, "margins": 0.0}
pixels, kernel, margin = c._pixels, c._block_means, c._margin_valid


def timed(name, f):
    def g(*a):
        t0 = time.perf_counter()
        try:
            return f(*a)
        finally:
            spent[name] += time.perf_counter() - t0

    return g


c._pixels, c._block_means, c._margin_valid = timed("pixels", pixels), timed("kernel", kernel), timed("margins", margin)
with open_bed(cfg, cache_folder()) as bed:
    w = grid_window(cfg, bed)
    t0 = time.perf_counter()
    c.coarse_mean(bed, w.x0, w.y0, w.ny, w.nx, cfg.grid.dx, pixel_factor(cfg.grid.dx, cfg.mesh.analysis_pixel), workers)
    print(f"workers {workers}: {time.perf_counter() - t0:.1f} s; thread-seconds {spent}")
