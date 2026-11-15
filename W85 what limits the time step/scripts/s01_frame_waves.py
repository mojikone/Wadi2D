"""W85 step 2: from a finished run's saved frames, the wave speed the step rule would read at every face.

    python s01_frame_waves.py <run folder> <grid cache .h5> <out folder> [hour ...]

CPU only. The tables come from the run's own cache file, the levels and mean depths from ``results.h5``; face
velocities are not saved, so every face starts at rest and the kernel's sum reduces to its gravity part: the saved
cell speed is added beside it as ``speed + celerity``. Writes ``waves_<hour>.npz`` (per cell: the larger wave of its
west and north faces, the cell's own data) and prints the ranking.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import h5py
import numpy as np

from wadi2d.config.schema import Numerics
from wadi2d.io.cache import load_tables
from wadi2d.solver.layout import TILE
from wadi2d.solver.limiter import tile_waves
from wadi2d.solver.model import Model
from wadi2d.solver.state import plan_field

CUTS = (0.20, 0.25, 0.30, 0.40, 0.50, 0.75, 1.00)
"""Steps, s, under which a face is counted as a limiter."""


def frame_at(maps, hour: float):
    names = sorted(maps)
    times = np.array([maps[n].attrs["t_s"] for n in names])
    n = int(np.argmin(np.abs(times - hour * 3600.0)))
    return names[n], float(times[n])


def waves_of(model: Model, dt: float) -> tuple[np.ndarray, np.ndarray]:
    """(ny, nx) wave speed of every west face and every north face."""
    grid = model.grid
    wx = np.zeros(grid.shape, np.float32)
    wy = np.zeros(grid.shape, np.float32)
    for t in range(1, grid.ntiles):
        tj, ti = grid.tiles[t]
        a, b, _u, _v = tile_waves(model.backend, t, dt)
        wx[tj * TILE : (tj + 1) * TILE, ti * TILE : (ti + 1) * TILE] = a
        wy[tj * TILE : (tj + 1) * TILE, ti * TILE : (ti + 1) * TILE] = b
    return wx, wy


def main() -> None:
    run, cache, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    hours = [float(a) for a in sys.argv[4:]] or [48.0]
    out.mkdir(parents=True, exist_ok=True)
    cfg = json.loads((run / "config.resolved.json").read_text())
    num = Numerics(**cfg["numerics"])
    tables = load_tables(cache, cache.stem.removeprefix("grid_"))
    if tables is None:
        raise SystemExit(f"{cache} is not a table cache this code reads")
    grid = tables.grid
    model = Model(tables, num, backend="cpu")
    dx = grid.dx
    summary = []
    with h5py.File(run / "results.h5", "r") as f:
        maps = f["maps"]
        for hour in hours:
            name, t = frame_at(maps, hour)
            d = maps[name]["depth"][()].astype(np.float64)
            h = maps[name]["mean_depth"][()].astype(np.float64)
            speed = maps[name]["speed"][()]
            if d.shape != grid.shape:
                raise SystemExit(f"frame {d.shape} against grid {grid.shape}")
            b = model.backend
            b.set_field("h", model.host.to_state(h))
            b.set_field("d", model.host.to_state(d))
            om = plan_field(tables, h)
            b.set_field("om", model.host.to_state(om))
            for a in ("u", "v", "mx", "my", "qx", "qy"):
                getattr(b, a)[:] = 0.0
            wx, wy = waves_of(model, 1e-3)
            w = np.maximum(wx, wy)
            both = w + speed  # at rest the kernel's sum is the celerity; the saved speed stands in for |u|
            dt_cell = num.cfl * dx / np.maximum(both, num.wave_floor)
            order = np.argsort(both, axis=None)[::-1][:25]
            jj, ii = np.unravel_index(order, both.shape)
            x, y = grid.xy_of(jj, ii)
            rows = [
                {
                    "x": float(x[n]), "y": float(y[n]), "j": int(jj[n]), "i": int(ii[n]),
                    "wave": float(both[jj[n], ii[n]]), "celerity": float(w[jj[n], ii[n]]),
                    "axis": "x" if wx[jj[n], ii[n]] >= wy[jj[n], ii[n]] else "y",
                    "speed": float(speed[jj[n], ii[n]]), "depth": float(d[jj[n], ii[n]]),
                    "mean_depth": float(h[jj[n], ii[n]]), "plan": float(om[jj[n], ii[n]]),
                    "bed": float(tables.zmin[jj[n], ii[n]]), "dt": float(dt_cell[jj[n], ii[n]]),
                }
                for n in range(order.size)
            ]  # fmt: skip
            counts = {f"{c:.2f}": int((dt_cell < c).sum()) for c in CUTS}
            tiles = {
                f"{c:.2f}": int(np.unique((np.argwhere(dt_cell < c) // TILE), axis=0).shape[0]) for c in CUTS
            }
            wet = int((d > num.h_cfl).sum())
            entry = {
                "hour": hour, "frame": name, "t_s": t, "dt_all": float(dt_cell.min()), "wet_cells": wet,
                "cells_under": counts, "tiles_under": tiles, "top": rows,
            }  # fmt: skip
            summary.append(entry)
            np.savez_compressed(
                out / f"waves_{hour:05.2f}h.npz", wx=wx, wy=wy, speed=speed, depth=d.astype(np.float32),
                mean_depth=h.astype(np.float32), plan=om.astype(np.float32), x0=grid.x0, y0=grid.y0, dx=dx,
            )  # fmt: skip
            print(
                f"\n== hour {hour} ({name}, t = {t:.0f} s): step from the frame {dt_cell.min():.4f} s, {wet} wet cells"
            )
            print("   cells under a step of", counts)
            print("   tiles holding them   ", tiles)
            for r in rows[:12]:
                print(
                    f"   ({r['x']:.0f}, {r['y']:.0f}) {r['axis']} wave {r['wave']:6.2f} = c {r['celerity']:6.2f} + u {r['speed']:5.2f}"
                    f"  depth {r['depth']:6.2f} mean {r['mean_depth']:7.3f} plan {r['plan']:.4f} bed {r['bed']:8.2f} dt {r['dt']:.3f}"
                )
    (out / "frame_waves.json").write_text(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
