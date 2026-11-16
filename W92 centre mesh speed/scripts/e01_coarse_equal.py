"""Whether the store's block mean equals GDAL's average read (``read_coarse``) bit for bit, on pieces of a job's
grid window or on the whole of it.

    python e01_coarse_equal.py <job.json> [whole]

Pieces: the window's corners and middle, 200 x 200 cells each, so a piece holds the raster's edge, the domain's no-data
and plain ground. ``whole``: the full window, both ways, timed.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from s01_mesh import cache_folder


def main() -> None:
    from wadi2d.breaklines.window import pixel_factor
    from wadi2d.demstore import open_bed
    from wadi2d.demstore.coarse import coarse_mean
    from wadi2d.mesh.streams import read_coarse
    from wadi2d.run import grid_window, load_job

    cfg = load_job(Path(sys.argv[1]))
    whole = len(sys.argv) > 2 and sys.argv[2] == "whole"
    dx = cfg.grid.dx
    factor = pixel_factor(dx, cfg.mesh.analysis_pixel)
    with open_bed(cfg, cache_folder()) as bed:
        w = grid_window(cfg, bed)
        if whole:
            pieces = [(0, 0, w.ny, w.nx)]
        else:
            n = 200
            pieces = [(0, 0, n, n), (w.ny - n, w.nx - n, n, n), (w.ny // 2, w.nx // 2, n, n), (0, w.nx - n, n, n),
                      (w.ny - n, 0, n, n), (-20, -20, 60, 60), (w.ny // 3, w.nx // 4, n, n)]  # fmt: skip
        for j0, i0, ny, nx in pieces:
            x0, y0 = w.x0 + i0 * dx, w.y0 - j0 * dx
            t0 = time.perf_counter()
            a = read_coarse(cfg.terrain.dem, x0, y0, ny, nx, dx, factor)
            t1 = time.perf_counter()
            b = coarse_mean(bed, x0, y0, ny, nx, dx, factor)
            t2 = time.perf_counter()
            same = a.shape == b.shape and np.array_equal(a, b, equal_nan=True)
            nan = int(np.isnan(a).sum())
            diff = 0 if same else int((~((a == b) | (np.isnan(a) & np.isnan(b)))).sum())
            print(f"piece {j0},{i0} {ny}x{nx}: shape {a.shape}, nan {nan}, identical {same}, differing {diff}, gdal {t1 - t0:.1f} s, store {t2 - t1:.1f} s", flush=True)
            if not same:
                bad = np.argwhere(~((a == b) | (np.isnan(a) & np.isnan(b))))[:5]
                for r, c in bad:
                    print("   ", r, c, repr(a[r, c]), repr(b[r, c]))


if __name__ == "__main__":
    main()
