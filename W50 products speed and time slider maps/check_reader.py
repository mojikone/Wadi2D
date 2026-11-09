"""The DEM reader after W50 against the reader before it (`dem_before.py`, the file at the commit before), on Block 2's
real DEM: the domain mask, and windows inside the DEM, across its edge and outside it. Every array must be identical.

    .venv\Scripts\python "W50 products speed and time slider maps\check_reader.py"
"""

from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from wadi2d.config.schema import RunConfig  # noqa: E402
from wadi2d.run import grid_window  # noqa: E402
from wadi2d.terrain.dem import RasterBed  # noqa: E402

spec = importlib.util.spec_from_file_location("dem_before", HERE / "dem_before.py")
old = importlib.util.module_from_spec(spec)
sys.modules["dem_before"] = old
spec.loader.exec_module(old)

cfg = RunConfig.model_validate_json((HERE / "profile" / "block2_b20" / "config.resolved.json").read_text(encoding="utf-8"))
with RasterBed(cfg.terrain.dem, cfg.terrain.pixel_stride) as new_bed, old.RasterBed(cfg.terrain.dem, cfg.terrain.pixel_stride) as old_bed:
    w = grid_window(cfg, new_bed)
    t = time.perf_counter(); m_new = new_bed.active_mask(w, cfg.grid.dx); tn = time.perf_counter() - t
    t = time.perf_counter(); m_old = old_bed.active_mask(w, cfg.grid.dx); to = time.perf_counter() - t
    print(f"domain mask: identical {bool(np.array_equal(m_new, m_old))}, cells {int(m_new.sum())}, new {tn:.1f} s, old {to:.1f} s")
    for b in (new_bed, old_bed):
        b.bind(w.x0, w.y0)
    cases = {"inside": (20000, 20000, 1280, 6000), "across the east edge": (20000, w.nx * 40 - 3000, 1280, 6000),
             "across the north edge": (-600, 10000, 1280, 4000), "a strip of Block 2": (36000, 0, 1280, 60240), "outside": (-9000, -9000, 512, 512)}
    for name, (r, c, nr, nc) in cases.items():
        a, bb = new_bed.read(r, c, nr, nc), old_bed.read(r, c, nr, nc)
        nf = new_bed.read(r, c, nr, nc, fill=False)
        same = bool(np.array_equal(a, bb))
        holes = int(np.isnan(nf).sum())
        print(f"  {name:24s} identical {same}  holes {holes}  fill=False agrees where not a hole {bool(np.array_equal(nf[~np.isnan(nf)], a[~np.isnan(nf)]))}")
