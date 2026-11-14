"""The rain split on the straight valley: 70 mm only within 30 m of the axis or only beyond it, turned 30 degrees
against the same on the lattice (the truth). Writes `split_vs_true.json`."""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.argv = sys.argv[:1]
import race_cases as rc  # noqa: E402

out: dict = {}
for where in ("near", "hills"):
    ref = rc.read(f"split_{where}_straight", ["sq5"])["sq5"]
    r = rc.read(f"split_{where}_rot30", ["sq5", "ce20"])
    print(f"\nrain {where} only: truth (lattice 5 m squares) s3 {ref['s3']['peak']:.1f} m3/s at {ref['s3']['at_min']:.1f} min")
    out[where] = {"truth_s3": ref["s3"]["peak"]}
    for m, v in r.items():
        rel = {n: 100 * (v[n]["peak"] / ref[n]["peak"] - 1) for n in ("s1", "s2", "s3")}
        print(f"  rot30 {m:5s} s3 {v['s3']['peak']:6.1f} {rel['s3']:+6.2f} %  t {v['s3']['at_min'] - ref['s3']['at_min']:+5.1f} min  [s1 {rel['s1']:+.2f} %  s2 {rel['s2']:+.2f} %]")
        out[where][m] = {"s3_peak": v["s3"]["peak"], "vs_true_pct": rel}
(HERE / "split_vs_true.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
