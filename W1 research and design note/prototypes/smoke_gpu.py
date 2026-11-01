"""First light of the production solver on both backends: still water, dam break, timing."""
import sys
import time
import warnings

import numpy as np

warnings.simplefilter("ignore")
from wadi2d.config.schema import Numerics, Tables  # noqa: E402
from wadi2d.grid import TileGrid  # noqa: E402
from wadi2d.solver.layout import TILE  # noqa: E402
from wadi2d.solver.model import Model  # noqa: E402
from wadi2d.tables import ArrayBed, build_tables, hbar_at_level  # noqa: E402
from scipy.ndimage import gaussian_filter  # noqa: E402

backend = sys.argv[1] if len(sys.argv) > 1 else "gpu"
rng = np.random.default_rng(1)
nx, ny, k, dx = 62, 62, 8, 10.0
zs = gaussian_filter(rng.normal(0, 1.0, (ny * k + 8, nx * k + 8)), 6) * 40 + 1500.0
mask = np.ones((ny, nx), bool)
grid = TileGrid.from_mask(mask, 0.0, 0.0, dx)
print("grid", grid.shape, "tiles", grid.ntiles - 1)
bed = ArrayBed(zs, dx / k)
t0 = time.time()
tables = build_tables(grid, bed, Tables(), 0.03)
print(f"tables {time.time() - t0:.2f} s")
m = Model(tables, Numerics(), backend)
level = float(np.median(zs))
hc = grid.from_tiles(tables.hc)
dtab = grid.from_tiles(tables.dtab)
hb = np.where(grid.mask, hbar_at_level(level, tables.zmin, hc, dtab), 0.0)
m.set_depth(hb)
v0 = m.volume()
t0 = time.time()
m.advance(600.0)
print(f"{m.backend.name} lake: steps {m.stepper.nsteps}, wall {time.time() - t0:.2f} s, max|u| {np.abs(m.field('u')).max():.2e}, max|v| {np.abs(m.field('v')).max():.2e}, mass {m.volume() / v0 - 1:+.1e}")

# dam break along x on a flat bed
nx, ny, k, dx = 400, 30, 1, 2.5
grid = TileGrid.from_mask(np.ones((ny, nx), bool), 0.0, 0.0, dx)
z = np.zeros((grid.shape[0] + 4, grid.shape[1] + 4))
tables = build_tables(grid, ArrayBed(z, dx), Tables(), 1e-5)
m = Model(tables, Numerics(cfl=0.45, e_wet=1e-5, sheet_flow=False, dt_every=1), backend)
xc, _ = grid.xy_of(np.zeros(grid.shape[1], int), np.arange(grid.shape[1]))
x0 = 500.0
h0 = np.where(xc < x0, 10.0, 2.0)
m.set_depth(np.tile(h0, (grid.shape[0], 1)))
v0 = m.volume()
t0 = time.time()
m.advance(30.0)
h = m.field("h")[grid.shape[0] // 2]
print(f"{m.backend.name} stoker: plateau {h[int(round((x0 + 0.5 * 9.388 * 30) / dx))]:.3f} vs 5.079, steps {m.stepper.nsteps}, wall {time.time() - t0:.2f} s, mass {m.volume() / v0 - 1:+.1e}")
