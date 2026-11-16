"""The floor rule's ground (``read_window``) of a job saved, timed, so the code before and after can be compared.

    python e03_window_equal.py save <job.json> <label>      # with PYTHONPATH on the code to time
    python e03_window_equal.py compare <label a> <label b>

``save`` hands the new code the domain mask as ``prepare_grid`` does (read from the cache, as there) and the store's
folder; the old code reads its own. Writes ``runs/<label>.window.npz`` and prints the seconds.
"""

from __future__ import annotations

import inspect
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from s01_mesh import RUNS, cache_folder, peak_gb


def save(job: str, label: str) -> None:
    from wadi2d.breaklines.window import read_window
    from wadi2d.demstore import open_bed
    from wadi2d.run import grid_window, kept_domain_mask, load_job

    cfg = load_job(Path(job))
    cache = cache_folder()
    extra = {}
    if "domain" in inspect.signature(read_window).parameters:
        with open_bed(cfg, cache) as bed:
            extra = {"domain": kept_domain_mask(cfg, bed, grid_window(cfg, bed), cache), "cache_dir": cache}
    t0 = time.perf_counter()
    win = read_window(cfg, **extra)
    seconds = time.perf_counter() - t0
    np.savez(RUNS / f"{label}.window.npz", z=win.z, inside=win.inside, meta=np.array([win.x0, win.y0, win.pixel, win.dx]))
    print(f"read_window {seconds:.1f} s, shape {win.z.shape}, {peak_gb()}")


def compare(a: str, b: str) -> None:
    x, y = np.load(RUNS / f"{a}.window.npz"), np.load(RUNS / f"{b}.window.npz")
    for name in ("z", "inside", "meta"):
        same = x[name].shape == y[name].shape and x[name].dtype == y[name].dtype and np.array_equal(x[name], y[name], equal_nan=True)
        print(name, x[name].shape, x[name].dtype, "identical" if same else "DIFFERENT")
        if not same and x[name].shape == y[name].shape:
            bad = ~((x[name] == y[name]) | (np.isnan(x[name]) & np.isnan(y[name])))
            print("   differing", int(bad.sum()), "first", np.argwhere(bad)[:5].tolist())


if __name__ == "__main__":
    if sys.argv[1] == "save":
        save(sys.argv[2], sys.argv[3])
    else:
        compare(sys.argv[2], sys.argv[3])
