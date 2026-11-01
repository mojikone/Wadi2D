"""At what level does the pool escape around the crest lines, and through which faces."""
import sys
from pathlib import Path

import numpy as np
import rasterio

sys.path.insert(0, r"D:\Mojtaba\Renardet\Wadi2D\W1 research and design note\validation\block2_full\scripts")
from common import CACHE, DEM
from dams import DAM_LIST, GGC_MINUS_NSA, NSA2
from dams import job as dam_job
from s10_eav import RES, connected, lowest_cell

from wadi2d.config.schema import RunConfig
from wadi2d.run import prepare_grid
from wadi2d.terrain import apply_objects

for dam in DAM_LIST.values():
    for label, dem, shift in (("NSA", NSA2, 0.0),):
        for dx in (20.0, 10.0):
            j = dam_job(dam, "leak", dx, np.array([0.0, 3600.0]), np.array([0.0, 0.0]), 3600.0, dem=dem, shift=shift)
            cfg = RunConfig.model_validate(j)
            tables, _ = prepare_grid(cfg, Path(CACHE))
            grid = tables.grid
            crest = apply_objects(grid, cfg.terrain.objects, 2.0).crest
            xc, yc = np.isfinite(crest.xz), np.isfinite(crest.yz)
            seed = lowest_cell(tables, RES[dam.name])
            lo, hi = dam.fsl, dam.crest + 6.0
            base = connected(tables, seed, lo, xc, yc).sum()
            for _ in range(11):
                mid = 0.5 * (lo + hi)
                if connected(tables, seed, mid, xc, yc).sum() > 3 * base + 2000:
                    hi = mid
                else:
                    lo = mid
            a = connected(tables, seed, lo, xc, yc)
            b = connected(tables, seed, hi, xc, yc)
            new = b & ~a
            from scipy import ndimage

            edge = ndimage.binary_dilation(a) & new
            jj, ii = np.nonzero(edge)
            x, y = grid.xy_of(jj, ii)
            print(dam.name, label, dx, f"escape level {hi:.2f} (crest {dam.crest})", "cells at the escape:", [(round(float(p)), round(float(q))) for p, q in zip(x, y)][:6], "zmin", np.round(tables.zmin[jj, ii][:6], 2).tolist())
