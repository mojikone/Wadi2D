"""Score the rotated straight valley (rain and the low inflow wave) against the same valley on the lattice, whose
answer is the truth for both, since turning the ground changes nothing physical. Writes `rotated_vs_true.json`."""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.argv = sys.argv[:1]
import race_cases as rc  # noqa: E402

MESHES = ["sq20", "sq10", "sq5", "sq2", "ce30", "ce20", "ce10", "ce5"]
out: dict = {}
for case, truth_case, truth_mesh in (("rain_rot30", "rain_straight", "sq2"), ("wave_low_rot30", "wave_low_straight", "sq5")):
    ref = rc.read(truth_case, [truth_mesh])[truth_mesh]
    r = rc.read(case, MESHES)
    print(f"\n{case} against {truth_case} {truth_mesh} (s3 {ref['s3']['peak']:.1f} m3/s at {ref['s3']['at_min']:.1f} min)")
    out[case] = {"truth": {"case": truth_case, "mesh": truth_mesh, "s3_peak": ref["s3"]["peak"], "s3_at_min": ref["s3"]["at_min"]}}
    for m, v in r.items():
        rel = {n: 100 * (v[n]["peak"] / ref[n]["peak"] - 1) for n in ("s1", "s2", "s3")}
        print(f"  {m:5s} s3 {v['s3']['peak']:6.1f} {rel['s3']:+6.2f} %  t {v['s3']['at_min'] - ref['s3']['at_min']:+5.1f} min"
              f"  [s1 {rel['s1']:+.2f} %  s2 {rel['s2']:+.2f} %]  steps {v['steps']}  loop {v['loop_s']:.0f} s")
        out[case][m] = {"s3_peak": v["s3"]["peak"], "vs_true_pct": rel, "dt_peak_min": v["s3"]["at_min"] - ref["s3"]["at_min"],
                        "steps": v["steps"], "loop_s": v["loop_s"]}
(HERE / "rotated_vs_true.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
