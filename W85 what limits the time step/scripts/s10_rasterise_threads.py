"""W85: GDAL's rasterise from many threads at once, against the same calls on one thread.

    python s10_rasterise_threads.py [threads] [rounds] [locked|free] [env]

``env`` gives each thread one rasterio environment for its whole life, in place of one made and dropped per call.

Each call burns one buffered line into a tile-sized window with its own transform, as a burn line's or a shaped
object's pixel edit does when the tables are built on threads (W81). ``locked`` takes ``wadi2d.terrain.rasterise``
(one call at a time) in place of rasterio's own. Prints how many calls warned (NotGeoreferencedWarning) and how many
masks differ from the single-thread ones, and by how many pixels.
"""

from __future__ import annotations

import sys
import threading
import warnings
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import rasterio
import shapely
from rasterio import features
from rasterio.errors import NotGeoreferencedWarning
from rasterio.transform import Affine

SHAPE = (641, 641)
PIXEL = 0.5


def jobs(n: int) -> list:
    """(strip, transform) of n calls: lines at every angle through windows spread over 20 km."""
    rng = np.random.default_rng(85)
    out = []
    for _ in range(n):
        west, north = 400000.0 + rng.integers(0, 40000) * PIXEL, 2700000.0 - rng.integers(0, 40000) * PIXEL
        cx, cy = west + 0.5 * SHAPE[1] * PIXEL, north - 0.5 * SHAPE[0] * PIXEL
        a = rng.uniform(0.0, np.pi)
        half = rng.uniform(40.0, 400.0)
        line = shapely.LineString(
            [(cx - half * np.cos(a), cy - half * np.sin(a)), (cx + half * np.cos(a), cy + half * np.sin(a))]
        )
        out.append(
            (
                line.buffer(rng.uniform(0.5, 12.0), cap_style="flat"),
                Affine(PIXEL, 0.0, west, 0.0, -PIXEL, north),
            )
        )
    return out


def main() -> None:
    threads = int(sys.argv[1]) if len(sys.argv) > 1 else 16
    rounds = int(sys.argv[2]) if len(sys.argv) > 2 else 4000
    locked = len(sys.argv) > 3 and sys.argv[3] == "locked"
    if locked:
        from wadi2d.terrain.rasterise import rasterize
    else:
        rasterize = features.rasterize
    work = jobs(rounds)
    held = threading.local()
    keep_env = len(sys.argv) > 4 and sys.argv[4] == "env"

    def one(job) -> tuple[np.ndarray, int]:
        strip, transform = job
        if keep_env and not hasattr(held, "env"):  # one GDAL environment per thread for its whole life
            held.env = rasterio.Env()
            held.env.__enter__()
        with warnings.catch_warnings(record=True) as got:
            warnings.simplefilter("always")
            hit = rasterize(
                [(strip, 1)], out_shape=SHAPE, transform=transform, all_touched=True, dtype="uint8"
            )
        return hit, sum(issubclass(w.category, NotGeoreferencedWarning) for w in got)

    alone = [one(job) for job in work]
    with ThreadPoolExecutor(threads) as pool:
        together = list(pool.map(one, work))
    warned = sum(w > 0 for _hit, w in together)
    wrong = [int((a != b).sum()) for (a, _w), (b, _v) in zip(alone, together, strict=True)]
    differing = [n for n in wrong if n]
    print(
        f"{'locked' if locked else 'rasterio'}: {rounds} calls on {threads} threads: {warned} warned,"
        f" {len(differing)} masks differ from the single-thread ones"
        + (f" (by {min(differing)} to {max(differing)} pixels)" if differing else "")
        + f"; alone: {sum(w > 0 for _hit, w in alone)} warned, {sum(int(h.sum()) for h, _w in alone)} pixels burned"
    )


if __name__ == "__main__":
    main()
