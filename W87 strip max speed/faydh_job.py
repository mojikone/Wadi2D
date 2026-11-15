"""W87 on real ground: W46's Faydh 01 job at 20 m with the aligned centre mesh (``faydh20_centres_wide.json``, CPU,
16 h), its grid cache in the work folder and a map every hour, so the strip's speed of record is in saved maps too.

    .venv\\Scripts\\python "W87 strip max speed\\faydh_job.py" <work folder>
    .venv\\Scripts\\python -m wadi2d.engine.cli run <work folder>\\faydh20_centres.json --out <work folder>\\after
    .venv\\Scripts\\python "W87 strip max speed\\run_bounded.py" <work folder>\\faydh20_centres.json <work folder>\\bounded both
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

if __name__ == "__main__":
    work = Path(sys.argv[1])
    work.mkdir(parents=True, exist_ok=True)
    source = ROOT / "W46 centre-based mesh generator" / "race_faydh" / "faydh20_centres_wide.json"
    job = json.loads(source.read_text(encoding="utf-8"))
    job["grid"]["cache_dir"] = str(work / "cache")
    job["outputs"]["map_every_s"] = 3600.0
    (work / "faydh20_centres.json").write_text(json.dumps(job, indent=1), encoding="utf-8")
    print("job written:", work / "faydh20_centres.json")
