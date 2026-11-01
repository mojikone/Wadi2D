"""Restart from a 6-hourly snapshot's mean depth, take a few steps, and name the tile and cell that set the wave speed."""
import sys
from pathlib import Path
import h5py, numpy as np
sys.path.insert(0, r"D:\Mojtaba\Renardet\Wadi2D\W1 research and design note\validation\block2_full\scripts")
from common import CACHE
from wadi2d.config.schema import RunConfig
from wadi2d.run import load_job, prepare_grid
from wadi2d.solver.model import Model
from wadi2d.solver.layout import TILE

run, snap = sys.argv[1], sys.argv[2]
cfg = load_job(f"jobs/{run}.json")
tables, _ = prepare_grid(cfg, Path(CACHE))
f = h5py.File(f"runs/{run}/results.h5", "r")
h = f["maps"][snap]["mean_depth"][()]
m = Model(tables, cfg.numerics, "gpu")
m.set_depth(h)
m.advance(30.0)
b = m.backend
cp = b.cp
w = cp.asnumpy(b.wave)
print("dt", m.stepper.dt, "max wave", w.max(), "implied dt", 0.45 * 20 / w.max())
order = np.argsort(w)[::-1][:6]
g = m.grid
d, hh = m.field("d"), m.field("h")
u, v = m.field("u"), m.field("v")
om = from_om = None
try:
    from wadi2d.solver.state import from_state
    om = from_state(g, cp.asnumpy(b.om))
except Exception as e:
    print("no om", e)
for t in order:
    tj, ti = g.tiles[t]
    sl = (slice(tj * TILE, (tj + 1) * TILE), slice(ti * TILE, (ti + 1) * TILE))
    x0, y0 = g.x0 + ti * TILE * g.dx, g.y0 - tj * TILE * g.dx
    du = np.maximum(np.abs(u[sl]), np.abs(v[sl]))
    msg = f"tile {t} wave {w[t]:.2f} at ({x0:.0f},{y0:.0f}) max d {d[sl].max():.2f} max h {hh[sl].max():.2f} max |u| {du.max():.2f}"
    if om is not None:
        o = om[sl]; wet = d[sl] > 0.01
        k = np.unravel_index(np.argmin(np.where(wet, o, 9.0)), o.shape)
        cx, cy = x0 + (k[1] + .5) * g.dx, y0 - (k[0] + .5) * g.dx
        msg += f"; smallest plan {o[k]:.4f} at ({cx:.0f},{cy:.0f}) d {d[sl][k]:.3f} h {hh[sl][k]:.4f} zbar-zmin {tables.zbar[sl][k]-tables.zmin[sl][k]:.2f}"
    print(msg)
print("plan_min", cfg.numerics.plan_min, "cells wet with plan<0.02", int(((om < 0.02) & (d > 0.01)).sum()) if om is not None else None)
