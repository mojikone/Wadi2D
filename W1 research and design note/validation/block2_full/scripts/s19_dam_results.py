"""2D routing against a level-pool Modified Puls on the EAV. Writes dam_results.json."""
import json
import sys

import numpy as np
import shapely

sys.path.insert(0, r"D:\Mojtaba\Renardet\Wadi2D\W1 research and design note\validation\block2_full\scripts")
from analyze import done_event, series
from common import OUT
from dams import DAM_LIST, modified_puls, tied

T0 = 43200.0
index = json.loads((OUT / "dam_jobs.json").read_text(encoding="utf-8"))
res = {}
for name, info in index.items():
    run = OUT / "runs" / name
    if not (run / "series").exists():
        print(name, "no series")
        continue
    dam = DAM_LIST[info["dam"]]
    t, level = series(run, "pool", "point")
    # column 1 is depth; the level is the third column
    import csv

    rows = np.array(list(csv.reader((run / "series" / "point_pool.csv").open()))[1:], dtype=np.float64)
    head = list(csv.reader((run / "series" / "point_pool.csv").open()))[0]
    z = rows[:, head.index("level_m")]
    tq, qa = series(run, "axis")
    qa = np.abs(qa)
    tq2, qs = series(run, "spillway")
    qs = np.abs(qs)
    z0 = float(np.interp(T0, t, z))
    spill_before = float(np.interp(T0, tq, qa))
    inflow = np.loadtxt(OUT / f"inflow_{info['dam'].replace(' ', '')}_{info['tag']}.csv", delimiter=",", skiprows=1)
    ts = inflow[:, 0] * 3600.0
    crest_len = sum(shapely.LineString(c).length for c in tied(dam)[:1])
    mp = modified_puls(dam, ts, inflow[:, 1], z0, crest_len)
    after = t >= T0
    k = int(np.argmax(np.where(tq >= T0, qa, -1.0)))
    d = done_event(run)["done"]
    out = {"dam": info["dam"], "tag": info["tag"], "dx": info["dx"], "z0_2d": z0, "q_at_t0": spill_before,
           "inflow_peak": float(inflow[:, 1].max()), "mp_peak": mp["peak_out"], "mp_t_h": mp["t_peak_h"], "mp_level": mp["peak_level"],
           "d2_peak": float(qa[k]), "d2_t_h": float((tq[k] - T0) / 3600.0), "d2_level": float(z[after].max()),
           "d2_spill_line_peak": float(qs[tq >= T0].max()), "crest": dam.crest, "fsl": dam.fsl,
           "over_crest": bool(z[after].max() > dam.crest), "loop_s": d["loop_s"] if d else None, "steps": d["steps"] if d else None,
           "balance": d["balance"]["relative_error"] if d else None}
    res[name] = out
    print(f"{name:26s} z0 {z0:7.2f} Q(t0) {spill_before:6.1f} | in {out['inflow_peak']:7.1f} | MP {mp['peak_out']:7.1f} @{mp['t_peak_h']:5.2f} z {mp['peak_level']:7.2f} | 2D {out['d2_peak']:7.1f} @{out['d2_t_h']:5.2f} z {out['d2_level']:7.2f} spill line {out['d2_spill_line_peak']:7.1f} | ratio {out['d2_peak']/max(mp['peak_out'],1e-9):.3f} dz {out['d2_level']-mp['peak_level']:+.2f}")
(OUT / "dam_results.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
