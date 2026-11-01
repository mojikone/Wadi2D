"""The same jobs on the later engine snapshot against the frozen one."""
import csv, sys
import numpy as np
sys.path.insert(0, "scripts")
from analyze import done_event, series, line_stats
from common import OUT
T0 = 43200.0
for name in ("dam_Bidah03_100yr_10", "dam_Bidah03_PMP_10_split", "dam_Faydh01_PMP_10_split"):
    for tag, run in (("3f32ca6", OUT/"runs"/name), ("63d580c", OUT/"runs"/f"head_{name}")):
        rows = list(csv.reader((run/"series"/"point_pool.csv").open()))
        h = rows[0]; a = np.array(rows[1:], dtype=float)
        z = a[a[:,0]>=T0, h.index("level_m")].max()
        t, q = series(run, "axis"); q = np.abs(q)
        msg = f"{name:28s} {tag} axis peak {q[t>=T0].max():7.1f} level {z:7.2f}"
        if "split" in name:
            for n in ("crest_before", "crest_after"):
                t, c = series(run, n); msg += f" {n} {np.abs(c[t>=T0]).max():6.1f}"
        print(msg, "loop", done_event(run)["done"]["loop_s"])
for tag, run in (("3f32ca6", OUT/"runs"/"c20_A74_h100"), ("63d580c", OUT/"runs"/"head_c20_A74_h100")):
    d = done_event(run)["done"]
    print(tag, "loop", d["loop_s"], "steps", d["steps"], {s: (round(line_stats(run, s)["peak"]), round(line_stats(run, s)["t_h"], 2), round(line_stats(run, s)["vol_m3"]/1e6, 2)) for s in ("Faydh 01", "Bidah 03", "R5A", "R2A", "Z4C")})
