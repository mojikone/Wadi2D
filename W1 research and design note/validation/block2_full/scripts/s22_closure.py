import json, sys, csv
import numpy as np
sys.path.insert(0, r"D:\Mojtaba\Renardet\Wadi2D\W1 research and design note\validation\block2_full\scripts")
from analyze import done_event, series
from common import OUT
T0 = 43200.0
for name in json.loads((OUT / "dam_jobs.json").read_text(encoding="utf-8")):
    for suffix in ("", "_split"):
        run = OUT / "runs" / f"{name}{suffix}"
        if not (run / "progress.jsonl").exists() or (suffix == "_split" and "PMP" not in name):
            continue
        b = done_event(run)["done"]["balance"]
        t, q = series(run, "axis"); q = np.abs(q)
        v = np.trapezoid(q, t)
        msg = f"{name+suffix:32s} in {b['inflow_m3']/1e6:7.2f} axis {v/1e6:7.2f} boundary {b['outflow_m3']/1e6:7.2f} store {b['storage_end_m3']/1e6:6.2f} err {b['relative_error']:.1e}"
        if suffix:
            for n in ("crest_before", "crest_after"):
                t, c = series(run, n)
                msg += f" | {n} peak {np.abs(c[t>=T0]).max():7.2f} vol {np.trapezoid(np.abs(c), t)/1e3:8.1f} km3"
        print(msg)
