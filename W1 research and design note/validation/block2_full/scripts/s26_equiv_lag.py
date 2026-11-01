"""The lag an SCS unit hydrograph would need to reproduce the 2D hydrograph of a headwater subbasin.

Same excess as HMS, grid search on the lag, best fit to the 2D ring hydrograph (least squares, 5 min steps); so the
difference with HMS can be read as one number. Run after the Manning runs.
"""
import json
import sys

import numpy as np

sys.path.insert(0, r"D:\Mojtaba\Renardet\Wadi2D\W1 research and design note\validation\block2_full\scripts")
from analyze import series
from common import HEADWATERS, HMS, OUT
from lumped_ref import GRID, TIMES_H, run_at

from wadi2d.hms import load_basin
from wadi2d.hydrology.transforms import ScsUnitHydrograph, convolve

basin = load_basin(HMS / "Basin_1.basin")
out = {}
for name in sys.argv[1:]:
    run = OUT / "runs" / name
    area = json.loads((run / "config.resolved.json").read_text(encoding="utf-8"))["storm"]["storm_area_km2"]
    result = run_at(area)
    rows = {}
    for s in HEADWATERS:
        e = basin.subbasins[s]
        excess = result.water[s].excess
        t, q = series(run, f"{s} ring")
        tmax = t.max() / 3600.0
        keep = TIMES_H <= tmax
        q5 = np.interp(TIMES_H[keep] * 3600.0, t, q)
        best = (1e30, None, None)
        for lag in np.arange(5.0, 240.0, 1.0):
            uh = ScsUnitHydrograph(float(lag)).unit_hydrograph(e.area, GRID.dt_minutes)
            f = convolve(excess, uh, GRID.n_times)[keep]
            err = float(((f - q5) ** 2).sum())
            if err < best[0]:
                best = (err, float(lag), float(f.max()))
        rows[s] = {"hms_lag": float(e.transform.lag), "equiv_lag": best[1], "peak_2d": float(q5.max()), "peak_fit": best[2]}
    out[name] = rows
    print(name, {k: (v["hms_lag"], v["equiv_lag"]) for k, v in rows.items()})
(OUT / "equivalent_lag.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
