"""Where a run's products spend their time (W50, 2026-11-09): Block 2 at 20 m, W49's local-radius run.

The run's configuration and results are copied here, so W49's run folder stays as it was, and the product step is
remade with the engine's own `remake`, every progress event stamped with the wall clock, under cProfile. Writes
`profile/stages.json` (seconds per stage, from the first to the last event of each), `profile/top.txt` (the 40
functions with the most cumulative time) and the products themselves in `profile/block2_b20/pixels`.

    .venv\Scripts\python "W50 products speed and time slider maps\profile_products.py"
"""

from __future__ import annotations

import cProfile
import io
import json
import pstats
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
from wadi2d.io import progress as progress_mod  # noqa: E402
from wadi2d.products.runner import remake  # noqa: E402

SOURCE = ROOT / "W49 local hydraulic radius face table" / "validation_reruns" / "block2_b20_local_radius"
RUN = HERE / "profile" / "block2_b20"

STAMPS: list[tuple[float, str, dict]] = []
_emit = progress_mod.Progress.emit


def stamped(self, ev, **fields):
    STAMPS.append((time.perf_counter(), ev, fields))
    return _emit(self, ev, **fields)


if __name__ == "__main__":
    RUN.mkdir(parents=True, exist_ok=True)
    for name in ("config.resolved.json", "results.h5"):
        shutil.copy2(SOURCE / name, RUN / name)
    progress_mod.Progress.emit = stamped
    t0 = time.perf_counter()
    prof = cProfile.Profile()
    code = prof.runcall(remake, RUN, None, False)
    total = time.perf_counter() - t0
    stages: dict[str, list[float]] = {}
    for t, ev, f in STAMPS:
        key = f.get("stage") or f.get("kind") or ev
        stages.setdefault(key, [t, t])[1] = t
    order = sorted(stages.items(), key=lambda kv: kv[1][0])
    out = {"total_s": total, "code": code, "stages": [{"stage": k, "from_s": a - t0, "to_s": b - t0, "span_s": b - a} for k, (a, b) in order]}
    (HERE / "profile" / "stages.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    s = io.StringIO()
    pstats.Stats(prof, stream=s).sort_stats("cumulative").print_stats(40)
    (HERE / "profile" / "top.txt").write_text(s.getvalue(), encoding="utf-8")
    print(f"total {total:.0f} s, exit {code}")
    for r in out["stages"]:
        print(f"  {r['stage']:22s} {r['from_s']:8.1f} to {r['to_s']:8.1f} s  ({r['span_s']:.1f} s)")
