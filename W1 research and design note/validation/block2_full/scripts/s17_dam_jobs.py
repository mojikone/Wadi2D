"""2D dam routing jobs: reservoir prefilled to FSL, then the inflow hydrograph, on the terrain the EAV came from.

The engine starts dry and has no initial level, so the prefill is a constant inflow of exactly the model's volume to
FSL over 10 h, then 2 h of rest; the design hydrograph starts at t = 12 h.
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, r"D:\Mojtaba\Renardet\Wadi2D\W1 research and design note\validation\block2_full\scripts")
from common import OUT, write_job
from dams import DAM_LIST, GGC_MINUS_NSA, NSA2
from dams import job as dam_job
from lumped_ref import GRID, TIMES_H, inflow_at, stats

T_FILL = 36000.0
RAMP = 600.0
T0 = 43200.0
INJECT = {"Bidah 03": (438300.0, 2726860.0), "Faydh 01": (430960.0, 2732900.0)}
eav = json.loads((OUT / "eav_check.json").read_text(encoding="utf-8"))
index = {}
for tag, met in (("100yr", "FM_100yr.met"), ("PMP", "FM_PMP.met")):
    for name, dam in DAM_LIST.items():
        q = inflow_at(name, met)
        s = stats(q)
        print(name, tag, f"inflow peak {s['peak']:.1f} at {s['t_h']:.2f} h, volume {s['vol_m3']/1e6:.2f} Mm3")
        np.savetxt(OUT / f"inflow_{name.replace(' ', '')}_{tag}.csv", np.column_stack((TIMES_H, q)), delimiter=",", header="t_h,q_m3s", comments="")
        dam.inject = INJECT[name]
        for dx in (20.0, 10.0):
            rows = eav[f"{name} | NSA 2 m | {dx:g}"]
            vfsl = float(np.interp(dam.fsl, [r["z"] for r in rows], [r["model_V"] for r in rows]))
            qf = vfsl / (T_FILL - RAMP)
            t = [0.0, RAMP, T_FILL - RAMP, T_FILL, T0]
            f = [0.0, qf, qf, 0.0, 0.0]
            keep = TIMES_H * 3600.0 <= 129600.0
            times = np.concatenate((t, T0 + TIMES_H[keep][1:] * 3600.0))
            flows = np.concatenate((f, q[keep][1:]))
            job_name = f"dam_{name.replace(' ', '')}_{tag}_{dx:g}"
            j = dam_job(dam, job_name, dx, times, flows, T0 + 129600.0, dem=NSA2)
            write_job(j, job_name)
            index[job_name] = {"dam": name, "tag": tag, "dx": dx, "vfsl": vfsl, "qfill": qf}
            print("  ", job_name, f"V(FSL) model {vfsl/1e6:.3f} Mm3, prefill {qf:.1f} m3/s")
(OUT / "dam_jobs.json").write_text(json.dumps(index, indent=1), encoding="utf-8")
print(" ".join(index))
