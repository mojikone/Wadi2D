"""What the saved Block 2 runs say of their active tiles: read progress.jsonl and the resolved job (read only)."""

import json
import sys
from pathlib import Path

RUNS = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(r"D:\Mojtaba\Renardet\Wadi2D\W79 Block 2 four ways\runs")
for r in ["rerun_run1_full_2d_aligned", "rerun_run3_hybrid_aligned", "rerun_run4_hybrid_2d_routing_aligned"]:
    rows = [json.loads(line) for line in (RUNS / r / "progress.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    acts = [x.get("active_tiles") for x in rows if "active_tiles" in x]
    print(r, len(rows), "first", acts[:4], "min", min(acts), "max", max(acts), "last", acts[-1])
    print("  keys", list(rows[-1].keys()))
    print("  first", rows[0])
    print("  last", rows[-1])
    c = json.loads((RUNS / r / "config.resolved.json").read_text(encoding="utf-8"))
    print("  top", {k: (v if not isinstance(v, dict | list) else type(v).__name__) for k, v in c.items()})
    print("  numerics", c.get("numerics"))
    print("  strips", {k: v for k, v in (c.get("strips") or {}).items() if not isinstance(v, list | dict)})
