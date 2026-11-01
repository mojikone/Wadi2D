"""The faces through which the pool first leaves, by the invert of each face."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, r"D:\Mojtaba\Renardet\Wadi2D\W1 research and design note\validation\block2_full\scripts")
from common import CACHE
from dams import DAM_LIST, NSA2
from dams import job as dam_job
from s10_eav import RES, connected, lowest_cell

from wadi2d.config.schema import RunConfig
from wadi2d.run import prepare_grid
from wadi2d.solver.layout import CLOSED
from wadi2d.terrain import apply_objects

for name, dx, level in (("Bidah 03", 20.0, 104.1), ("Faydh 01", 20.0, 233.9), ("Faydh 01", 10.0, 233.9)):
    dam = DAM_LIST[name]
    cfg = RunConfig.model_validate(dam_job(dam, "leak", dx, np.array([0.0, 3600.0]), np.array([0.0, 0.0]), 3600.0, dem=NSA2))
    tables, _ = prepare_grid(cfg, Path(CACHE))
    g = tables.grid
    crest = apply_objects(g, cfg.terrain.objects, 2.0).crest
    xc, yc = np.isfinite(crest.xz), np.isfinite(crest.yz)
    a = connected(tables, lowest_cell(tables, RES[name]), level, xc, yc)
    fx, fy = g.from_tiles(tables.flx), g.from_tiles(tables.fly)
    z = tables.zmin
    out = []
    ny, nx = a.shape
    for j, i in zip(*np.nonzero(a)):
        for bj, bi, fj, fi, f, c, n in ((j, i + 1, j, i + 1, fx, xc, (j, i)), (j, i - 1, j, i, fx, xc, (j, i - 1)), (j + 1, i, j + 1, i, fy, yc, (j, i)), (j - 1, i, j, i, fy, yc, (j - 1, i))):
            if 0 <= bj < ny and 0 <= bi < nx and g.mask[bj, bi] and not a[bj, bi] and not c[fj, fi] and f[fj, fi] < CLOSED * 0.5:
                inv = z[n] + f[fj, fi]
                x, y = g.xy_of(np.array(j), np.array(i))
                x2, y2 = g.xy_of(np.array(bj), np.array(bi))
                out.append((float(inv), round(float(x)), round(float(y)), round(float(x2)), round(float(y2))))
    out.sort()
    print(name, dx, "lowest open faces leaving the pool:", out[:8])
