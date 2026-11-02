"""plan_min 0.05 against the frozen Bidah rain-on-grid jobs: one setting changes, nothing else. The baseline runs are the
ones already compared with HEC-RAS 6.6 in W1 validation/ras_rain_on_grid.md.

Pass mark, fixed before running: peak at the Bidah section within 1 % of the baseline at both cell sizes, ratio to RAS
still within the +/-10 % band, time of peak within 2 min, mass error under 1e-6. Writes jobs/.
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE.parent / "W1 research and design note" / "validation" / "ras_rain_on_grid" / "jobs"
(HERE / "jobs").mkdir(exist_ok=True)
for name in ("20m_n050_em", "10m_n050_em"):
    job = json.loads((SRC / f"{name}.json").read_text(encoding="utf-8"))
    job["project"]["name"] = f"{name}_planmin05"
    job.setdefault("numerics", {})["plan_min"] = 0.05
    (HERE / "jobs" / f"{name}_planmin05.json").write_text(json.dumps(job, indent=1), encoding="utf-8")
    print(name, job["numerics"])
