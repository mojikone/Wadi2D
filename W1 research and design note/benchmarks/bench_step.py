"""Measured cost of one solver step with real sub-grid tables, on the GPU.

A rough sloping domain of N cells, all wet, built from 10 x 10 pixels per cell. Prints ms per step, nanoseconds per
cell-step and what that means for a 48 h run. Usage: bench_step.py [cells_side ...]
"""
import sys
import time
import warnings

import numpy as np
from scipy.ndimage import gaussian_filter

warnings.simplefilter("ignore")
from wadi2d.config.schema import Numerics, Tables  # noqa: E402
from wadi2d.grid import TileGrid  # noqa: E402
from wadi2d.solver.model import Model  # noqa: E402
from wadi2d.tables import ArrayBed, build_tables  # noqa: E402

sizes = [int(a) for a in sys.argv[1:]] or [512, 1024, 2048]
for side in sizes:
    k, dx = 4, 10.0
    tg = TileGrid.from_mask(np.ones((side, side), bool), 0.0, 0.0, dx)
    ny, nx = tg.shape
    rng = np.random.default_rng(0)
    # a coarse field upsampled, so the table build stays short and the relief stays realistic
    coarse = gaussian_filter(rng.normal(0, 1.0, (ny // 8 + 4, nx // 8 + 4)), 3) * 30
    z = np.kron(coarse, np.ones((8 * k, 8 * k)))[: ny * k + 2, : nx * k + 2] + 0.003 * dx / k * np.arange(nx * k + 2)
    t0 = time.perf_counter()
    tables = build_tables(tg, ArrayBed(z, dx / k), Tables(), 0.03)
    tb = time.perf_counter() - t0
    m = Model(tables, Numerics(), "gpu")
    m.stepper.adaptive_active = False
    m.set_depth(np.where(tg.mask, 2.0, 0.0))
    m.advance(20.0)
    n0 = m.stepper.nsteps
    m.backend.synchronize()
    t0 = time.perf_counter()
    while m.stepper.nsteps < n0 + 400:
        m.backend.step(0.2, False, False)
        m.stepper.nsteps += 1
    m.backend.synchronize()
    w = (time.perf_counter() - t0) / 400
    cells = int(tg.mask.sum())
    print(
        f"{cells / 1e6:.2f} M cells: tables {tb:.1f} s; {w * 1e3:.3f} ms/step; {w / cells * 1e9:.3f} ns per cell-step; "
        f"{cells / w / 1e9:.2f} GCUPS; 48 h at 1 s step: {172800 * w / 60:.1f} min"
    )
    del m
