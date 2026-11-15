"""W87: what a finished run's record holds, read from its files alone (no GPU, nothing rerun): the strip's speed
maxima over thresholds and by cell kind, what the cells held where the saved maps spike, and the squares over 10 m/s
sorted by where they sit: on a join with the strip (an active square beside a square the strip replaced), within two
cells of one, or away from any.

    .venv\\Scripts\\python "W87 strip max speed\\block2_record.py" <run folder> [<out.json>]
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import h5py
import numpy as np

LIMITS = (5.0, 10.0, 25.0, 35.36, 100.0, 1e4)


def read(run: Path) -> dict:
    cfg = json.loads((run / "config.resolved.json").read_text(encoding="utf-8"))
    found: dict = {
        "run": run.name,
        "u_max": cfg["numerics"]["u_max"],
        "speed_depth": cfg["outputs"]["speed_depth"],
        "dx": cfg["grid"]["dx"],
    }
    with h5py.File(run / "results.h5", "r") as f:
        x0, y0, dx = float(f.attrs["x0"]), float(f.attrs["y0"]), float(f.attrs["dx"])
        found["mass_error"] = float(f.attrs["relative_error"])
        mask = f["mask"][()].astype(bool)
        mx = f["maxima"]
        sq, sd, sh = mx["speed"][()], mx["depth"][()], mx["mean_depth"][()]
        s, d, h, dv = (mx[n][0] for n in ("strip_speed", "strip_depth", "strip_mean_depth", "strip_hazard"))
        spikes = []
        for name in sorted(f["maps"].keys()):
            g = f["maps"][name]
            if "strip_speed" not in g:
                continue
            sp = g["strip_speed"][0]
            over = sp > 10.0
            if over.any():
                spikes.append(
                    (
                        float(np.median(g["strip_mean_depth"][0][over])),
                        float(np.median(g["strip_depth"][0][over])),
                        int(over.sum()),
                        float(sp.max()),
                    )
                )
        found["maps"] = len(f["maps"])
    found["strip"] = {"cells": int(s.size), "speed_max": float(s.max()), "hazard_max": float(dv.max())} | {
        f"over_{lim:g}": int((s > lim).sum()) for lim in LIMITS
    }
    over = s > 10.0
    found["strip"]["over_10_mean_depth_over_level_median"] = float(
        np.median(h[over] / np.maximum(d[over], 1e-9))
    )
    found["strip"]["wet_mean_depth_over_level_median"] = float(np.median((h / np.maximum(d, 1e-9))[d > 0.05]))
    if spikes:
        a = np.array(spikes)
        found["maps_with_strip_over_10"] = {
            "maps": len(spikes), "cells_in_the_worst_map": int(a[:, 2].max()), "speed_max": float(a[:, 3].max()),
            "median_of_the_maps_median_mean_depth_m": float(np.median(a[:, 0])), "median_of_the_maps_median_level_m": float(np.median(a[:, 1])),
        }  # fmt: skip
    mesh = run / "maps" / "strip_mesh.gpkg"
    if mesh.is_file():
        db = sqlite3.connect(mesh)
        rows = db.execute("SELECT cell, kind, area_m2 FROM strip_cells").fetchall()
        db.close()
        kind = np.empty(s.size, object)
        area = np.zeros(s.size)
        for c, k, a_ in rows:
            kind[c], area[c] = k, a_
        tri = kind == "triangle"
        found["strip"]["by_kind"] = {
            "corridor_cells": int((~tri).sum()), "other_cells": int(tri.sum()),
            "corridor_over_10": int((over & ~tri).sum()), "other_over_10": int((over & tri).sum()),
            "corridor_over_100": int(((s > 100) & ~tri).sum()), "other_over_100": int(((s > 100) & tri).sum()),
            "area_median_all_m2": float(np.median(area)), "area_median_over_10_m2": float(np.median(area[over])),
        }  # fmt: skip
    pad = np.pad(mask, 1, constant_values=True)
    join = mask & (~pad[:-2, 1:-1] | ~pad[2:, 1:-1] | ~pad[1:-1, :-2] | ~pad[1:-1, 2:])
    grown = np.pad(join, 2)
    near = np.zeros_like(join)
    for a_ in range(5):
        for b_ in range(5):
            near |= grown[a_ : a_ + join.shape[0], b_ : b_ + join.shape[1]]
    hot = mask & (sq > 10.0)
    found["squares"] = {
        "active": int(mask.sum()),
        "beside_a_replaced_or_outside_square": int(join.sum()),
        "speed_max": float(sq.max()),
    } | {
        f"over_{lim:g}": [int((mask & (sq > lim)).sum()), int((mask & (sq > lim) & join).sum())]
        for lim in LIMITS
    }
    found["squares"]["over_10_on_a_join"] = int((hot & join).sum())
    found["squares"]["over_10_within_two_cells_of_a_join"] = int((hot & near & ~join).sum())
    away = hot & ~near
    j, i = np.nonzero(away)
    found["squares"]["over_10_away_from_any_join"] = [
        {"x": x0 + (b_ + 0.5) * dx, "y": y0 - (a_ + 0.5) * dx, "speed": float(sq[a_, b_]), "depth_m": float(sd[a_, b_]), "mean_depth_m": float(sh[a_, b_])}
        for a_, b_ in sorted(zip(j.tolist(), i.tolist(), strict=True), key=lambda p: -sq[p])
    ]  # fmt: skip
    return found


if __name__ == "__main__":
    result = read(Path(sys.argv[1]))
    text = json.dumps(result, indent=1)
    print(text)
    if len(sys.argv) > 2:
        Path(sys.argv[2]).write_text(text, encoding="utf-8")
