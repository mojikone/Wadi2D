"""The rewritten pieces against the code before them, in one process, on random and on Block 2's own inputs.

    python e05_pieces_equal.py [<s01 label for a mesh pickle>]

The old modules are loaded from ``runs/old`` under other names: ``MeshGeometry.from_rings`` on random rings (with
repeats, single nodes, empty rings) and on the rings of a finished mesh; ``resample`` on random lines, plain and with
Z, smoothed and not.
"""

from __future__ import annotations

import importlib.util
import pickle
import sys
from pathlib import Path

import numpy as np
import shapely

RUNS = Path(__file__).resolve().parents[1] / "runs"
OLD = RUNS / "old" / "wadi2d"


def old_module(rel: str, name: str):
    spec = importlib.util.spec_from_file_location(name, OLD / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def same_geometry(g, h) -> bool:
    return all(np.array_equal(getattr(g, n), getattr(h, n)) and getattr(g, n).dtype == getattr(h, n).dtype for n in ("x", "y", "ring_start", "ring_node", "face_node", "face_cell"))


def main() -> None:
    from wadi2d.strips.geometry import MeshGeometry
    from wadi2d.strips.mesher import resample

    old_geo = old_module("strips/geometry.py", "old_geometry").MeshGeometry
    old_resample = old_module("strips/mesher.py", "old_mesher").resample
    rng = np.random.default_rng(7)
    bad = 0
    for _trial in range(300):
        n = int(rng.integers(1, 60))
        rings = [rng.integers(0, max(3, n // 2), int(rng.integers(0, 9))) for _ in range(n)]
        x, y = rng.random(max(3, n // 2)), rng.random(max(3, n // 2))
        bad += not same_geometry(MeshGeometry.from_rings(x, y, rings), old_geo.from_rings(x, y, rings))
    print("from_rings on random rings: mismatches", bad, "of 300")
    bad = 0
    for trial in range(200):
        m = int(rng.integers(2, 40))
        xy = np.cumsum(rng.standard_normal((m, 2)) * 50.0, axis=0) + 500000.0
        if trial % 2:
            xy = np.column_stack((xy, rng.random(m) * 100.0))
        line = shapely.LineString(xy)
        for step, smooth in ((20.0, 0), (20.0, 5), (7.3, 3), (1000.0, 5)):
            a, b = resample(line, step, smooth), old_resample(line, step, smooth)
            bad += not (a.shape == b.shape and a.dtype == b.dtype and np.array_equal(a, b))
    print("resample on random lines: mismatches", bad, "of 800")
    if len(sys.argv) > 1:
        with open(RUNS / f"{sys.argv[1]}.mesh.pkl", "rb") as f:
            _mask, strip = pickle.load(f)
        g = strip.geometry
        rings = [g.ring(c) for c in range(g.ncells)]
        print("from_rings on", sys.argv[1], "identical" if same_geometry(MeshGeometry.from_rings(g.x, g.y, rings), old_geo.from_rings(g.x, g.y, rings)) else "DIFFERENT")


if __name__ == "__main__":
    main()
